"""Relay state machine (room mode). Server-authoritative, polled, lazily ticked.

lobby → compose → read → reveal → edit → read → reveal → … → compose (next maker) … → ended

This module knows nothing about metrics. The service passes callbacks:
  on_reveal(room, rnd) -> result dict  (fidelity, scores, landed, status)  — called once when a read phase ends
It only moves phases, enforces who may act, and keeps the record straight.
"""
from __future__ import annotations

import secrets
import string
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

ROOM_LOCK = threading.RLock()
CONSONANTS = "BCDFGHJKLMNPQRSTVWXZ"
_ALPHABET = string.ascii_letters + string.digits + "-_"

T_COMPOSE = 90
T_READ_V0 = 60
T_READ_VN = 45
T_REVEAL = 30
T_EDIT = 45
REPLAY_READ = 10
REPLAY_REVEAL = 12
MIN_PLAYERS = 2


class RoomError(Exception):
    def __init__(self, detail: str, status: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def new_id(prefix: str, n: int = 10) -> str:
    return prefix + "".join(secrets.choice(_ALPHABET) for _ in range(n))


def new_code(store, coll: str = "rooms") -> str:
    for _ in range(50):
        code = "".join(secrets.choice(CONSONANTS) for _ in range(4))
        if store.get(coll, code) is None:
            return code
    raise RoomError("could not allocate a code", 500)


# --------------------------------------------------------------------------- helpers
def player(room: dict, guest_id: str | None) -> dict | None:
    for p in room["players"]:
        if p["guest_id"] == guest_id:
            return p
    return None


def nickname_of(room: dict, guest_id: str | None) -> str | None:
    p = player(room, guest_id)
    return p["nickname"] if p else None


def readers_of(room: dict, rnd: dict) -> list[str]:
    return [p["guest_id"] for p in room["players"] if p["guest_id"] != rnd["holder_id"]]


def _save(store, room: dict) -> dict:
    store.put("rooms", room)
    return room


def load(store, code: str) -> dict:
    room = store.get("rooms", code.upper())
    if room is None:
        raise RoomError("no such room", 404)
    return room


def _ends(now: datetime, seconds: int) -> str:
    return iso(now + timedelta(seconds=seconds))


# --------------------------------------------------------------------------- lobby
def create_room(store, deck: dict, nickname: str, guest_id: str | None) -> tuple[str, dict]:
    guest_id = guest_id or new_id("g_")
    nickname = (nickname or "").strip()[:24] or "anon"
    with ROOM_LOCK:
        code = new_code(store)
        now = iso(utcnow())
        room = {
            "id": code, "code": code, "deck_id": deck["id"], "deck_code": deck["code"], "host_id": guest_id,
            "created_at": now, "phase": "lobby",
            "players": [{"guest_id": guest_id, "nickname": nickname, "joined_at": now}],
            "turn_order": [guest_id], "maker_index": 0, "makers_done": [], "scores": {},
            "max_edits": int(deck.get("max_edits", 3)), "round": None, "history": [], "n_cards": 0,
        }
        _save(store, room)
    return guest_id, room


def join_room(store, code: str, nickname: str, guest_id: str | None) -> tuple[str, dict]:
    guest_id = guest_id or new_id("g_")
    nickname = (nickname or "").strip()[:24] or "anon"
    with ROOM_LOCK:
        room = load(store, code)
        p = player(room, guest_id)
        if p is None:
            if len(room["players"]) >= 12:
                raise RoomError("room is full (12)")
            room["players"].append({"guest_id": guest_id, "nickname": nickname, "joined_at": iso(utcnow())})
            room["turn_order"].append(guest_id)
        else:
            p["nickname"] = nickname or p["nickname"]
        _save(store, room)
    return guest_id, room


# --------------------------------------------------------------------------- phase moves (call under ROOM_LOCK)
def _next_maker(room: dict) -> str | None:
    """The next player in turn order who has not been maker; None when everyone has."""
    for k in range(len(room["turn_order"])):
        gid = room["turn_order"][(room["maker_index"] + k) % len(room["turn_order"])]
        if gid not in room["makers_done"] and player(room, gid) is not None:
            room["maker_index"] = room["turn_order"].index(gid)
            return gid
    return None


def _enter_compose(room: dict, now: datetime) -> None:
    maker = _next_maker(room)
    if maker is None:
        room["phase"] = "ended"
        room["round"] = None
        room["ended_at"] = iso(now)
        return
    room["n_cards"] += 1
    room["phase"] = "compose"
    room["round"] = {
        "n_card": room["n_cards"], "round_id": new_id("rd_"), "card_id": None, "version_id": None, "v": 0,
        "maker_id": maker, "holder_id": maker, "editor_id": None, "editors_used": [],
        "phase_ends_at": _ends(now, T_COMPOSE), "submitted_reader_ids": [], "reader_ids": [],
        "replay": False, "result": None,
    }


def _enter_read(room: dict, now: datetime, seconds: int) -> None:
    rnd = room["round"]
    room["phase"] = "read"
    rnd["reader_ids"] = readers_of(room, rnd)
    rnd["submitted_reader_ids"] = []
    rnd["phase_ends_at"] = _ends(now, seconds)
    rnd["result"] = None


def _enter_reveal(room: dict, now: datetime, on_reveal: Callable | None, seconds: int = T_REVEAL) -> None:
    rnd = room["round"]
    room["phase"] = "reveal"
    rnd["phase_ends_at"] = _ends(now, seconds)
    result = None
    if on_reveal is not None:
        try:
            result = on_reveal(room, rnd)
        except Exception as e:  # never block the reveal on scoring
            print(f"[relay] on_reveal failed: {type(e).__name__}: {e}")
            result = {"error": f"{type(e).__name__}: {e}"}
    rnd["result"] = result or {}
    if not rnd.get("replay"):
        for gid, pts in (rnd["result"].get("points") or {}).items():
            room["scores"][gid] = room["scores"].get(gid, 0) + int(pts)


def _next_editor(room: dict, rnd: dict) -> str | None:
    order = room["turn_order"]
    if rnd["holder_id"] not in order:
        return None
    start = order.index(rnd["holder_id"])
    for k in range(1, len(order) + 1):
        gid = order[(start + k) % len(order)]
        if gid != rnd["maker_id"] and player(room, gid) is not None:
            return gid
    return None


def _finish_card(room: dict, rnd: dict, now: datetime, note: str | None = None) -> None:
    room["history"].append({
        "n_card": rnd["n_card"], "card_id": rnd["card_id"], "maker_id": rnd["maker_id"],
        "v": rnd["v"], "status": (rnd.get("result") or {}).get("status"), "note": note, "replay": bool(rnd.get("replay")),
    })
    if rnd["maker_id"] not in room["makers_done"]:
        room["makers_done"].append(rnd["maker_id"])
    room["maker_index"] = (room["maker_index"] + 1) % max(1, len(room["turn_order"]))
    _enter_compose(room, now)


def _after_reveal(room: dict, now: datetime, on_close: Callable | None = None) -> None:
    rnd = room["round"]
    if rnd.get("replay"):
        _replay_advance(room, now)
        return
    status = (rnd.get("result") or {}).get("status", "reading")
    if status in ("landed", "closed"):
        _finish_card(room, rnd, now)
        return
    editor = _next_editor(room, rnd)
    if editor is None or rnd["v"] >= room["max_edits"]:
        if on_close:
            on_close(room, rnd, "no editor available" if editor is None else "edit budget spent")
        rnd["result"] = {**(rnd.get("result") or {}), "status": "closed"}
        _finish_card(room, rnd, now, note="no editor available" if editor is None else None)
        return
    room["phase"] = "edit"
    rnd["editor_id"] = editor
    rnd["holder_id"] = editor
    rnd["editors_used"].append(editor)
    rnd["phase_ends_at"] = _ends(now, T_EDIT)


# --------------------------------------------------------------------------- lazy tick
def tick(store, room: dict, now: datetime | None = None, on_reveal: Callable | None = None, on_close: Callable | None = None) -> dict:
    now = now or utcnow()
    if room["phase"] in ("lobby", "ended") or not room.get("round"):
        return room
    with ROOM_LOCK:
        room = load(store, room["code"])
        changed = False
        for _ in range(8):  # a stale room may need several transitions (e.g. after a long pause)
            rnd = room.get("round")
            if room["phase"] in ("lobby", "ended") or not rnd:
                break
            ends = parse_iso(rnd["phase_ends_at"]) if rnd.get("phase_ends_at") else None
            expired = ends is not None and now >= ends
            phase = room["phase"]
            if phase == "read":
                if rnd.get("replay"):
                    if not expired:
                        break
                else:
                    all_in = bool(rnd["reader_ids"]) and set(rnd["reader_ids"]) <= set(rnd["submitted_reader_ids"])
                    if not (all_in or expired):
                        break
                _enter_reveal(room, now, on_reveal, seconds=REPLAY_REVEAL if rnd.get("replay") else T_REVEAL)
                changed = True
            elif phase == "reveal":
                if not expired:
                    break
                _after_reveal(room, now, on_close)
                changed = True
            elif phase == "compose":
                if not expired:
                    break
                room["history"].append({"n_card": rnd["n_card"], "card_id": None, "maker_id": rnd["maker_id"], "v": 0,
                                        "status": "skipped", "note": "maker timed out", "replay": False})
                if rnd["maker_id"] not in room["makers_done"]:
                    room["makers_done"].append(rnd["maker_id"])
                room["maker_index"] = (room["maker_index"] + 1) % max(1, len(room["turn_order"]))
                _enter_compose(room, now)
                changed = True
            elif phase == "edit":
                if not expired:
                    break
                if on_close:
                    on_close(room, rnd, "editor timed out")
                rnd["result"] = {**(rnd.get("result") or {}), "status": "closed"}
                _finish_card(room, rnd, now, note="editor timed out")
                changed = True
            else:
                break
        if changed:
            _save(store, room)
        return room


# --------------------------------------------------------------------------- actions
def start(store, room: dict, guest_id: str) -> dict:
    with ROOM_LOCK:
        room = load(store, room["code"])
        if room["phase"] != "lobby":
            raise RoomError("already started")
        if guest_id != room["host_id"]:
            raise RoomError("only the host can start", 403)
        if len(room["players"]) < MIN_PLAYERS:
            raise RoomError(f"need at least {MIN_PLAYERS} players")
        room["small_room"] = len(room["players"]) < 3
        _enter_compose(room, utcnow())
        return _save(store, room)


def compose(store, room: dict, guest_id: str, card: dict, version: dict) -> dict:
    """compose → read. `card` and `version` are fully built docs (service validated and embedded)."""
    with ROOM_LOCK:
        room = load(store, room["code"])
        rnd = room.get("round")
        if room["phase"] != "compose" or not rnd:
            raise RoomError("not waiting for a composition")
        if guest_id != rnd["maker_id"]:
            raise RoomError("you are not this card's maker", 403)
        card["room_id"] = room["code"]
        card["maker_nickname"] = nickname_of(room, guest_id)
        store.put("cards", card)
        store.put("versions", version)
        rnd["card_id"] = card["id"]
        rnd["version_id"] = version["id"]
        rnd["v"] = 0
        _enter_read(room, utcnow(), T_READ_V0)
        return _save(store, room)


def submit_reading(store, room: dict, guest_id: str, reading: dict, on_reveal: Callable | None = None) -> dict:
    with ROOM_LOCK:
        room = load(store, room["code"])
        rnd = room.get("round")
        if room["phase"] != "read" or not rnd or rnd.get("replay"):
            raise RoomError("not accepting readings now")
        if guest_id == rnd["holder_id"]:
            raise RoomError("the card's holder does not read it")
        if player(room, guest_id) is None:
            raise RoomError("join the room first", 403)
        if guest_id in rnd["submitted_reader_ids"]:
            raise RoomError("you already answered this version")
        reading.update({"card_id": rnd["card_id"], "version_id": rnd["version_id"], "room_id": room["code"],
                        "round_id": rnd["round_id"], "nickname": nickname_of(room, guest_id), "deck_id": room["deck_id"]})
        store.put("readings", reading)
        rnd["submitted_reader_ids"].append(guest_id)
        _save(store, room)
        return tick(store, room, on_reveal=on_reveal)


def submit_edit(store, room: dict, guest_id: str, version: dict) -> dict:
    """edit → read (45 s). `version` is the fully built v+1 doc (service validated the move)."""
    with ROOM_LOCK:
        room = load(store, room["code"])
        rnd = room.get("round")
        if room["phase"] != "edit" or not rnd:
            raise RoomError("not waiting for an edit")
        if guest_id != rnd["editor_id"]:
            raise RoomError("you are not this turn's editor", 403)
        version["edit"]["editor_nickname"] = nickname_of(room, guest_id)
        store.put("versions", version)
        card = store.get("cards", rnd["card_id"])
        if card is not None:
            card["latest_version_id"] = version["id"]
            card["n_versions"] = int(version["v"]) + 1
            if guest_id not in card.get("encoder_ids", []):
                card.setdefault("encoder_ids", []).append(guest_id)
            store.put("cards", card)
        rnd["version_id"] = version["id"]
        rnd["v"] = int(version["v"])
        _enter_read(room, utcnow(), T_READ_VN)
        return _save(store, room)


def continue_reveal(store, room: dict, guest_id: str, on_reveal: Callable | None = None, on_close: Callable | None = None) -> dict:
    with ROOM_LOCK:
        room = load(store, room["code"])
        room = tick(store, room, on_reveal=on_reveal, on_close=on_close)
        rnd = room.get("round")
        if room["phase"] != "reveal" or not rnd:
            raise RoomError("nothing to continue from")
        if guest_id not in (room["host_id"], rnd["holder_id"], rnd["maker_id"]):
            raise RoomError("only the host or the card's holder can continue", 403)
        _after_reveal(room, utcnow(), on_close)
        return _save(store, room)


# --------------------------------------------------------------------------- replay
def start_replay(store, room: dict, guest_id: str, script: dict) -> dict:
    """script = {card_id, maker_id, maker_nickname, versions: [{version_id, v, readings: [reading docs]}], origin}.
    Each version's readings arrive over REPLAY_READ s, then a REPLAY_REVEAL s reveal, then the next version."""
    with ROOM_LOCK:
        room = load(store, room["code"])
        if guest_id != room["host_id"]:
            raise RoomError("only the host can start a replay", 403)
        if room["phase"] in ("read", "edit", "compose") and room.get("round") and not room["round"].get("replay"):
            raise RoomError("a live card is in progress")
        versions = script.get("versions") or []
        if not versions or not any(v.get("readings") for v in versions):
            raise RoomError("nothing to replay yet")
        now = utcnow()
        room["phase"] = "read"
        room["round"] = {
            "n_card": room["n_cards"], "round_id": new_id("rd_"), "card_id": script["card_id"], "version_id": versions[0]["version_id"],
            "v": int(versions[0]["v"]), "maker_id": script.get("maker_id"), "holder_id": script.get("maker_id"), "editor_id": None,
            "maker_nickname": script.get("maker_nickname"), "editors_used": [], "phase_ends_at": None,
            "submitted_reader_ids": [], "reader_ids": [], "replay": True, "replay_step": 0, "replay_versions": versions,
            "replay_origin": script.get("origin"), "result": None,
        }
        _stage_replay_step(room["round"], now)
        return _save(store, room)


def _stage_replay_step(rnd: dict, now: datetime) -> None:
    step = rnd["replay_step"]
    ver = rnd["replay_versions"][step]
    rs = ver.get("readings") or []
    gap = REPLAY_READ / max(1, len(rs))
    staged = []
    for i, r in enumerate(rs):
        rr = dict(r)
        rr["arrive_at"] = iso(now + timedelta(seconds=gap * (i + 1)))
        rr["synthetic"] = True
        rr["replay_of"] = rnd.get("replay_origin")
        staged.append(rr)
    rnd["version_id"] = ver["version_id"]
    rnd["v"] = int(ver["v"])
    rnd["holder_id"] = ver.get("editor_id") or rnd["maker_id"]
    rnd["editor_id"] = ver.get("editor_id")
    rnd["replay_readings"] = staged
    rnd["reader_ids"] = [r.get("reader_id") for r in rs]
    rnd["submitted_reader_ids"] = []
    rnd["phase_ends_at"] = iso(now + timedelta(seconds=REPLAY_READ + 1.5))
    rnd["result"] = None


def _replay_advance(room: dict, now: datetime) -> None:
    rnd = room["round"]
    if rnd["replay_step"] + 1 < len(rnd["replay_versions"]):
        rnd["replay_step"] += 1
        room["phase"] = "read"
        _stage_replay_step(rnd, now)
    else:
        # stay on the last reveal until the host continues → back to where the room was
        room["phase"] = "reveal"
        rnd["phase_ends_at"] = None
        rnd["replay_done"] = True


def end_replay(store, room: dict, guest_id: str) -> dict:
    with ROOM_LOCK:
        room = load(store, room["code"])
        rnd = room.get("round")
        if not rnd or not rnd.get("replay"):
            raise RoomError("no replay running")
        if guest_id != room["host_id"]:
            raise RoomError("only the host can end a replay", 403)
        room["round"] = None
        room["phase"] = "lobby" if not room["makers_done"] else "ended"
        if room["phase"] == "ended" and _next_maker(room) is not None:
            _enter_compose(room, utcnow())
        return _save(store, room)


def arrived_replay_readings(rnd: dict, now: datetime | None = None) -> list[dict]:
    now = now or utcnow()
    return [r for r in rnd.get("replay_readings", []) if parse_iso(r["arrive_at"]) <= now]


# --------------------------------------------------------------------------- views
def role_of(room: dict, guest_id: str | None) -> str:
    rnd = room.get("round")
    is_host = guest_id == room["host_id"]
    in_room = player(room, guest_id) is not None
    if room["phase"] in ("lobby", "ended") or not rnd:
        return "host" if is_host else ("player" if in_room else "spectator")
    if rnd.get("replay"):
        return "host" if is_host else ("player" if in_room else "spectator")
    if guest_id == rnd["holder_id"]:
        return "maker" if rnd["v"] == 0 and room["phase"] in ("compose", "read", "reveal") and guest_id == rnd["maker_id"] else "editor"
    if in_room:
        return "reader"
    return "spectator"


def view(room: dict, guest_id: str | None, now: datetime | None = None) -> dict:
    now = now or utcnow()
    out = {k: v for k, v in room.items() if k not in ("round", "id")}
    rnd = room.get("round")
    role = role_of(room, guest_id)
    if rnd is not None:
        r = {k: v for k, v in rnd.items() if k not in ("replay_readings", "replay_versions", "result")}
        if rnd.get("replay"):
            r["submitted_reader_ids"] = [x.get("reader_id") for x in arrived_replay_readings(rnd, now)]
            r["n_readers"] = len(rnd.get("replay_readings", []))
            r["maker_nickname"] = rnd.get("maker_nickname")
        else:
            r["n_readers"] = len(rnd.get("reader_ids") or readers_of(room, rnd))
            r["maker_nickname"] = nickname_of(room, rnd["maker_id"])
        r["n_submitted"] = len(r["submitted_reader_ids"])
        r["holder_nickname"] = rnd.get("maker_nickname") if rnd.get("replay") else nickname_of(room, rnd["holder_id"])
        r["editor_nickname"] = nickname_of(room, rnd["editor_id"]) if rnd.get("editor_id") else None
        r["max_edits"] = room["max_edits"]
        r["status"] = (rnd.get("result") or {}).get("status")
        out["round"] = r
    else:
        out["round"] = None
    out["server_time"] = iso(now)
    out["you"] = {"guest_id": guest_id, "role": role, "is_host": guest_id == room["host_id"],
                  "submitted": bool(rnd and guest_id in rnd.get("submitted_reader_ids", []))}
    return out

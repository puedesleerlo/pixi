"""Live sessions (spec §3.9, §5.7, §8.3): `reading` mode (host picks cards, readers read, reveal) and `relay`
mode (compose = choose an existing card → read → reveal → edit → read → reveal … until landed / max_edits →
summary). Server timers, lazy ticks, no websockets. Points live only in the session (Round.scores).

Session doc: spec §3.9 fields plus `turn_order`, `turn_index`, `current_round_id`, `rounds_done[]`, `scores{}` (summary).
Round doc: spec §3.9 fields plus `submitted[]`, `reader_ids[]`, `result` (frozen evaluate_version), `replay`.
Edits inside a relay come from the imaging job: the router builds the new Version (through service/cards) and
calls `attach_edit(...)`; while the job runs the session is in state `generating` with a timer; if it expires the
relay continues on the previous version and the edit lands asynchronously (spec §5.5).
"""
from __future__ import annotations

import threading
from datetime import timedelta

from pixie import relay as R
from service import measure, readings as RD

LOCK = threading.RLock()
DEFAULT_SETTINGS = {"read_timer": 60, "edit_timer": 45, "generation_timer": 40, "live_generation": False, "guests_allowed": True, "max_edits": 3}
T_REVEAL = 30
T_COMPOSE = 90
MIN_PLAYERS = 2


class SessionError(Exception):
    def __init__(self, detail: str, status: int = 400):
        super().__init__(detail)
        self.detail, self.status = detail, status


def _now():
    return R.utcnow()


def _ends(seconds: int) -> str:
    return R.iso(_now() + timedelta(seconds=seconds))


def _save(store, s: dict) -> dict:
    s["updated_at"] = R.iso(_now())
    store.put("sessions", s)
    return s


def load(store, sid: str) -> dict:
    s = store.get("sessions", sid)
    if s is None:
        raise SessionError("no such session", 404)
    return s


def by_code(store, code: str) -> dict:
    found = store.find("sessions", code=code.upper())
    live = [s for s in found if s.get("state") != "ended"]
    if not live:
        raise SessionError("no such session", 404)
    return live[-1]


def player(s: dict, uid: str | None) -> dict | None:
    return next((p for p in s["players"] if p["user_or_guest_id"] == uid), None)


def nick(s: dict, uid: str | None) -> str | None:
    p = player(s, uid)
    return p["nickname"] if p else None


# ----------------------------------------------------------------------------- create / join
def create(store, deck: dict, host_id: str, nickname: str, mode: str = "relay", settings: dict | None = None) -> dict:
    if mode not in ("reading", "relay"):
        raise SessionError("mode must be reading or relay", 422)
    with LOCK:
        code = R.new_code(store, "sessions")
        now = R.iso(_now())
        s = {"id": R.new_id("s_"), "deck_id": deck["id"], "code": code, "host_id": host_id, "mode": mode,
             "settings": {**DEFAULT_SETTINGS, "max_edits": int((deck.get("settings") or {}).get("max_edits_per_card", 3)) if mode == "relay" else 3, **(settings or {})},
             "players": [{"user_or_guest_id": host_id, "nickname": (nickname or "host")[:24], "role": "host", "connected": True, "is_guest": host_id.startswith("g_")}],
             "state": "lobby", "round_ends_at": None, "current_card_id": None, "current_version_id": None, "turn_order": [host_id], "turn_index": 0,
             "current_round_id": None, "rounds_done": [], "scores": {}, "makers_done": [], "created_at": now, "updated_at": now}
        return _save(store, s)


def join(store, s: dict, uid: str, nickname: str, is_guest: bool) -> dict:
    with LOCK:
        s = load(store, s["id"])
        if s["state"] == "ended":
            raise SessionError("this session has ended", 409)
        if is_guest and not s["settings"].get("guests_allowed", True):
            raise SessionError("guests are not allowed in this session", 403)
        p = player(s, uid)
        if p is None:
            if len(s["players"]) >= 30:
                raise SessionError("session is full")
            s["players"].append({"user_or_guest_id": uid, "nickname": (nickname or "anon")[:24], "role": "reader" if is_guest else "player", "connected": True, "is_guest": is_guest})
            if not is_guest:
                s["turn_order"].append(uid)
        else:
            p["nickname"] = (nickname or p["nickname"])[:24]
            p["connected"] = True
        return _save(store, s)


# ----------------------------------------------------------------------------- rounds
def _round(store, s: dict, kind: str, card: dict, version: dict, actor: str | None, seconds: int, replay: bool = False) -> dict:
    holder = actor
    readers = [p["user_or_guest_id"] for p in s["players"] if p["user_or_guest_id"] != holder and p["user_or_guest_id"] != card.get("maker_id") or (kind == "edit" and p["user_or_guest_id"] == card.get("maker_id") and p["user_or_guest_id"] != holder)]
    rd = {"id": R.new_id("rd_"), "session_id": s["id"], "deck_id": s["deck_id"], "kind": kind, "card_id": card["id"], "version_id": version["id"],
          "maker_or_editor_id": actor, "started_at": R.iso(_now()), "ended_at": None, "readings": [], "reader_ids": readers, "submitted": [],
          "effect": None, "scores": [], "result": None, "replay": replay}
    store.put("rounds", rd)
    s["current_round_id"] = rd["id"]
    s["current_card_id"] = card["id"]
    s["current_version_id"] = version["id"]
    s["state"] = "read"
    s["round_ends_at"] = _ends(seconds)
    return rd


def start(store, s: dict, uid: str) -> dict:
    with LOCK:
        s = load(store, s["id"])
        if uid != s["host_id"]:
            raise SessionError("only the host can start", 403)
        if s["state"] != "lobby":
            raise SessionError("already started", 409)
        if len(s["players"]) < MIN_PLAYERS:
            raise SessionError(f"need at least {MIN_PLAYERS} players")
        if s["mode"] == "relay":
            _enter_compose(store, s)
        else:
            s["state"] = "compose"  # host picks a card
            s["round_ends_at"] = None
        return _save(store, s)


def _next_maker(s: dict) -> str | None:
    order = [u for u in s["turn_order"] if player(s, u)]
    for k in range(len(order)):
        u = order[(s["turn_index"] + k) % len(order)]
        if u not in s["makers_done"]:
            s["turn_index"] = order.index(u)
            return u
    return None


def _enter_compose(store, s: dict) -> None:
    maker = _next_maker(s)
    if maker is None:
        s["state"] = "summary"
        s["round_ends_at"] = None
        return
    s["state"] = "compose"
    s["current_maker_id"] = maker
    s["current_card_id"] = None
    s["current_version_id"] = None
    s["round_ends_at"] = _ends(T_COMPOSE)


def choose_card(store, deck: dict, s: dict, uid: str, card: dict) -> dict:
    """compose → read. Relay: the current maker chooses one of THEIR cards (or any card in the deck if they have
    none). Reading mode: the host chooses any card in `reading`."""
    with LOCK:
        s = load(store, s["id"])
        if s["state"] != "compose":
            raise SessionError("not choosing a card now")
        if card.get("deck_id") != deck["id"]:
            raise SessionError("card is not in this deck", 404)
        if not card.get("current_version_id"):
            raise SessionError("this card has no version yet", 409)
        if s["mode"] == "relay":
            if uid != s.get("current_maker_id"):
                raise SessionError("it is not your turn to compose", 403)
        elif uid != s["host_id"]:
            raise SessionError("only the host picks cards in a reading session", 403)
        version = store.get("versions", card["current_version_id"])
        actor = s.get("current_maker_id") if s["mode"] == "relay" else card.get("maker_id")
        s["edits_this_card"] = 0
        _round(store, s, "read", card, version, actor, int(s["settings"]["read_timer"]))
        return _save(store, s)


def submit_reading(store, deck: dict, s: dict, uid: str, body: dict, embed_fn=None) -> dict:
    with LOCK:
        s = load(store, s["id"])
        s = tick(store, deck, s)
        if s["state"] != "read":
            raise SessionError("not accepting readings now")
        rd = store.get("rounds", s["current_round_id"])
        if rd.get("replay"):
            raise SessionError("this is a replay")
        if uid not in rd["reader_ids"]:
            raise SessionError("you are not a reader this round", 403)
        if uid in rd["submitted"]:
            raise SessionError("you already answered this round")
        version = store.get("versions", rd["version_id"])
        reading, _ = RD.submit(store, deck, version, uid, body, embed_fn=embed_fn, session_id=s["id"], round_id=rd["id"], nickname=nick(s, uid))
        rd["readings"].append(reading["id"])
        rd["submitted"].append(uid)
        store.put("rounds", rd)
        if set(rd["reader_ids"]) <= set(rd["submitted"]):
            _reveal(store, deck, s, rd)
        return _save(store, s)


def _reveal(store, deck: dict, s: dict, rd: dict) -> None:
    card = store.get("cards", rd["card_id"])
    version = store.get("versions", rd["version_id"])
    rs = [store.get("readings", rid) for rid in rd["readings"]]
    rs = [r for r in rs if r]
    prev = store.get("versions", version["base_version_id"]) if version.get("base_version_id") else None
    prev_rs = store.find("readings", version_id=prev["id"], session_id=s["id"]) if prev else []
    res = measure.evaluate_version(card, version, rs, prev_rs, int(s["settings"]["max_edits"]))
    scores = []
    if not rd.get("replay"):
        ms = res.get("maker_score")
        if ms and ms.get("points") is not None and card.get("maker_id"):
            scores.append({"user_id": card["maker_id"], "points": int(ms["points"]), "reason": "maker"})
        ef = res.get("edit_effect")
        if ef and ef.get("bet_hit") and ef.get("editor_id"):
            scores.append({"user_id": ef["editor_id"], "points": 2, "reason": "bet"})
        if res.get("landed"):
            for enc in dict.fromkeys(card.get("encoder_ids") or [card.get("maker_id")]):
                if enc:
                    scores.append({"user_id": enc, "points": 1, "reason": "landing"})
        for sc in scores:
            s["scores"][sc["user_id"]] = s["scores"].get(sc["user_id"], 0) + sc["points"]
        # the card's own status machine (async rules) also advances on session readings
        RD.advance_status(store, deck, card, version)
    rd.update({"ended_at": R.iso(_now()), "effect": res.get("edit_effect"), "scores": scores, "result": res})
    store.put("rounds", rd)
    s["state"] = "reveal"
    s["round_ends_at"] = _ends(T_REVEAL)


def advance(store, deck: dict, s: dict, uid: str) -> dict:
    """Leave `reveal` (host or the round's actor) or `summary`."""
    with LOCK:
        s = load(store, s["id"])
        s = tick(store, deck, s)
        if s["state"] == "reveal":
            rd = store.get("rounds", s["current_round_id"])
            if uid not in (s["host_id"], rd.get("maker_or_editor_id")):
                raise SessionError("only the host or the card's holder can continue", 403)
            _after_reveal(store, deck, s, rd)
        elif s["state"] == "summary":
            if uid != s["host_id"]:
                raise SessionError("only the host can end", 403)
            s["state"] = "ended"
        elif s["state"] == "generating":
            if uid != s["host_id"]:
                raise SessionError("only the host can skip a pending edit", 403)
            _skip_generation(store, deck, s)
        else:
            raise SessionError(f"nothing to advance from {s['state']}")
        return _save(store, s)


def _after_reveal(store, deck: dict, s: dict, rd: dict) -> None:
    s["rounds_done"].append(rd["id"])
    card = store.get("cards", rd["card_id"])
    res = rd.get("result") or {}
    if rd.get("replay"):
        s["state"] = "summary" if s["mode"] == "relay" else "compose"
        s["round_ends_at"] = None
        return
    if s["mode"] == "reading":
        s["state"] = "compose"
        s["round_ends_at"] = None
        return
    done = res.get("landed") or int(s.get("edits_this_card", 0)) >= int(s["settings"]["max_edits"])
    if done:
        if s.get("current_maker_id") and s["current_maker_id"] not in s["makers_done"]:
            s["makers_done"].append(s["current_maker_id"])
        s["turn_index"] = (s["turn_index"] + 1) % max(1, len(s["turn_order"]))
        _enter_compose(store, s)
        return
    editor = _next_editor(s, rd, card)
    if editor is None:
        _enter_compose(store, s)
        return
    s["state"] = "edit"
    s["current_editor_id"] = editor
    s["round_ends_at"] = _ends(int(s["settings"]["edit_timer"]))


def _next_editor(s: dict, rd: dict, card: dict) -> str | None:
    order = [u for u in s["turn_order"] if player(s, u)]
    if not order:
        return None
    holder = rd.get("maker_or_editor_id")
    start = order.index(holder) if holder in order else s["turn_index"]
    for k in range(1, len(order) + 1):
        u = order[(start + k) % len(order)]
        if u != card.get("maker_id") and u != s.get("current_maker_id"):
            return u
    return None


def begin_edit(store, s: dict, uid: str, job_id: str | None) -> dict:
    """The editor submitted an op; the imaging job runs. State `generating` with a timer."""
    with LOCK:
        s = load(store, s["id"])
        if s["state"] != "edit" or uid != s.get("current_editor_id"):
            raise SessionError("not your edit turn", 403)
        s["state"] = "generating"
        s["pending_job_id"] = job_id
        s["round_ends_at"] = _ends(int(s["settings"]["generation_timer"]))
        return _save(store, s)


def attach_edit(store, deck: dict, s: dict, version: dict) -> dict:
    """The new version exists (chosen candidate). Start the paired re-read (ghost markers, edit_timer)."""
    with LOCK:
        s = load(store, s["id"])
        card = store.get("cards", version["card_id"])
        if s["state"] not in ("generating", "edit"):
            # generation finished late: the edit lands asynchronously; nothing to do here
            return s
        s["edits_this_card"] = int(s.get("edits_this_card", 0)) + 1
        s["pending_job_id"] = None
        _round(store, s, "read", card, version, s.get("current_editor_id"), int(s["settings"]["edit_timer"]))
        return _save(store, s)


def _skip_generation(store, deck: dict, s: dict) -> None:
    """Generation exceeded its timer: continue with the previous version (spec §5.5)."""
    s["pending_job_id"] = None
    rd = store.get("rounds", s["current_round_id"])
    card = store.get("cards", rd["card_id"])
    editor = _next_editor(s, rd, card)
    if editor is None or int(s.get("edits_this_card", 0)) >= int(s["settings"]["max_edits"]):
        _enter_compose(store, s)
    else:
        s["state"] = "edit"
        s["current_editor_id"] = editor
        s["round_ends_at"] = _ends(int(s["settings"]["edit_timer"]))


def tick(store, deck: dict, s: dict) -> dict:
    """Lazy timer transitions."""
    with LOCK:
        s = load(store, s["id"])
        for _ in range(6):
            ends = R.parse_iso(s["round_ends_at"]) if s.get("round_ends_at") else None
            if ends is None or _now() < ends:
                break
            st = s["state"]
            if st == "read":
                rd = store.get("rounds", s["current_round_id"])
                _reveal(store, deck, s, rd)
            elif st == "reveal":
                _after_reveal(store, deck, s, store.get("rounds", s["current_round_id"]))
            elif st == "compose":
                if s["mode"] == "relay" and s.get("current_maker_id"):
                    s["makers_done"].append(s["current_maker_id"])
                    s["turn_index"] = (s["turn_index"] + 1) % max(1, len(s["turn_order"]))
                    _enter_compose(store, s)
                else:
                    s["round_ends_at"] = None
            elif st == "edit":
                rd = store.get("rounds", s["current_round_id"])
                card = store.get("cards", rd["card_id"])
                s["makers_done"].append(s.get("current_maker_id")) if s.get("current_maker_id") and s.get("current_maker_id") not in s["makers_done"] else None
                s["turn_index"] = (s["turn_index"] + 1) % max(1, len(s["turn_order"]))
                _enter_compose(store, s)
            elif st == "generating":
                _skip_generation(store, deck, s)
            else:
                s["round_ends_at"] = None
        return _save(store, s)


def end(store, s: dict, uid: str) -> dict:
    with LOCK:
        s = load(store, s["id"])
        if uid != s["host_id"]:
            raise SessionError("only the host can end", 403)
        s["state"] = "ended"
        s["round_ends_at"] = None
        return _save(store, s)


# ----------------------------------------------------------------------------- views
def view(store, deck: dict, s: dict, uid: str | None) -> dict:
    """The session as one participant sees it; readers never get the intent."""
    s = tick(store, deck, s)
    rd = store.get("rounds", s["current_round_id"]) if s.get("current_round_id") else None
    card = store.get("cards", s["current_card_id"]) if s.get("current_card_id") else None
    version = store.get("versions", s["current_version_id"]) if s.get("current_version_id") else None
    is_host = uid == s["host_id"]
    role = "host" if is_host else ("player" if player(s, uid) else "spectator")
    if s["state"] in ("compose",) and s["mode"] == "relay":
        role = "maker" if uid == s.get("current_maker_id") else role
    if s["state"] in ("edit", "generating"):
        role = "editor" if uid == s.get("current_editor_id") else role
    if rd and s["state"] in ("read", "reveal") and uid in (rd.get("reader_ids") or []):
        role = "reader"
    encoder = bool(card and (uid == card.get("maker_id") or uid in (card.get("encoder_ids") or []) or uid in (s.get("current_maker_id"), s.get("current_editor_id"))))
    out = {"id": s["id"], "code": s["code"], "deck_id": s["deck_id"], "host_id": s["host_id"], "mode": s["mode"], "settings": s["settings"],
           "players": s["players"], "state": s["state"], "round_ends_at": s.get("round_ends_at"), "server_time": R.iso(_now()),
           "turn_order": s["turn_order"], "turn_index": s["turn_index"], "scores": s["scores"], "rounds_done": s["rounds_done"],
           "current_maker_id": s.get("current_maker_id"), "current_editor_id": s.get("current_editor_id"), "edits_this_card": s.get("edits_this_card", 0),
           "you": {"id": uid, "role": role, "is_host": is_host, "submitted": bool(rd and uid in (rd.get("submitted") or []))}}
    if card and version:
        out["card"] = {"id": card["id"], "position_key": card.get("position_key"), "title": card.get("title"), "status": card.get("status"), "maker_id": card.get("maker_id"),
                       "maker_nickname": nick(s, card.get("maker_id"))}
        out["version"] = {"id": version["id"], "v": int(version.get("v", 0)), "image_url": version.get("image_url"), "thumb_url": version.get("thumb_url"),
                          "symbols_detected": version.get("symbols_detected", []), "how": version.get("how")}
        if encoder:
            intent = dict(card.get("intent") or {})
            rs_now = []
            if rd and rd.get("readings"):
                rs_now = [store.get("readings", rid) for rid in rd["readings"]]
                rs_now = [r for r in rs_now if r]
            elif s.get("rounds_done"):
                last = store.get("rounds", s["rounds_done"][-1])
                if last and last.get("card_id") == card["id"]:
                    rs_now = [store.get("readings", rid) for rid in last.get("readings", [])]
                    rs_now = [r for r in rs_now if r]
            if rs_now and intent.get("axes"):
                from pixie.metrics import gaps as _gaps

                intent["gaps_signed"] = [float(x) for x in _gaps(intent["axes"], [r["axes"] for r in rs_now])]
                intent["fidelity"] = measure.version_fidelity(card, rs_now)
            out["intent"] = intent
    if rd:
        out["round"] = {"id": rd["id"], "kind": rd["kind"], "n_readers": len(rd.get("reader_ids") or []), "n_submitted": len(rd.get("submitted") or []),
                        "maker_or_editor_id": rd.get("maker_or_editor_id"), "replay": rd.get("replay", False)}
        if version and version.get("base_version_id") and uid:
            prev = [r for r in store.find("readings", version_id=version["base_version_id"]) if r.get("reader_id") == uid]
            out["you"]["previous_axes"] = prev[0]["axes"] if prev else None
    if s["state"] == "reveal" and card and version and rd:
        rs = [store.get("readings", rid) for rid in rd["readings"]]
        rs = [r for r in rs if r]
        prev = store.get("versions", version["base_version_id"]) if version.get("base_version_id") else None
        prev_rs = store.find("readings", version_id=prev["id"], session_id=s["id"]) if prev else []
        try:
            out["reveal"] = measure.reveal(store, deck, card, version, uid, encoder, readings=rs, prev_readings=prev_rs)
            out["reveal"]["scores"] = rd.get("scores", [])
            ef = out["reveal"].get("edit_effect")
            if ef and ef.get("editor_id"):
                ef["editor_nickname"] = nick(s, ef["editor_id"])
        except Exception as e:  # never break polling
            out["reveal_error"] = f"{type(e).__name__}: {e}"
    if s["state"] == "summary" or s["state"] == "ended":
        out["summary"] = summary(store, s)
    return out


def summary(store, s: dict) -> dict:
    rounds = [store.get("rounds", rid) for rid in s.get("rounds_done", [])]
    rounds = [r for r in rounds if r]
    cards = []
    for rd in rounds:
        res = rd.get("result") or {}
        cards.append({"round_id": rd["id"], "kind": rd["kind"], "card_id": rd["card_id"], "version_id": rd["version_id"], "actor": nick(s, rd.get("maker_or_editor_id")),
                      "fidelity": res.get("fidelity"), "delta_fidelity": res.get("delta_fidelity"), "landed": res.get("landed"),
                      "bet": (res.get("edit_effect") or {}).get("bet_axis"), "bet_hit": (res.get("edit_effect") or {}).get("bet_hit"),
                      "shift": (res.get("edit_effect") or {}).get("shift"), "scores": rd.get("scores", [])})
    return {"cards": cards, "scores": [{"user_id": u, "nickname": nick(s, u), "points": p} for u, p in s.get("scores", {}).items()]}

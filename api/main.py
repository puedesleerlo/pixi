"""PIXIE API v4 — FastAPI routes. Thin: validation + store/engine calls. See docs/CONTRACT.md."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from pixie import relay as R
from pixie.embed import backend_name as embed_backend
from pixie.naming import naming_backend
from pixie.store import open_store

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("PIXIE_DATA_DIR", os.path.join(HERE, "..", "data"))
SNAPSHOT = os.environ.get("PIXIE_SNAPSHOT", os.path.join(HERE, ".pixie_state.json"))
STATIC_DIR = os.path.join(HERE, "static")
os.makedirs(STATIC_DIR, exist_ok=True)

state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    from service import Engine

    store = open_store(SNAPSHOT)
    state["store"] = store
    state["engine"] = Engine(DATA_DIR, store)
    yield
    store.flush()


app = FastAPI(title="PIXIE", version="0.4", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def engine():
    return state["engine"]


def store():
    return state["store"]


# ----------------------------------------------------------------------------- models
class JoinBody(BaseModel):
    nickname: str = Field(default="anon", max_length=24)
    guest_id: str | None = None
    deck_code: str | None = None


class GuestBody(BaseModel):
    guest_id: str


class Placement(BaseModel):
    element_id: str
    slot: str


class ComposeBody(BaseModel):
    guest_id: str
    statement: str = Field(min_length=1, max_length=140)
    axes: list[float] = Field(min_length=8, max_length=8)
    elements: list[Placement] = Field(min_length=2, max_length=5)
    approved_editors: str | list[str] | None = None


class ReadingBody(BaseModel):
    guest_id: str
    axes: list[float] = Field(min_length=8, max_length=8)
    free_text: str | None = Field(default=None, max_length=140)
    latency_ms: int | None = None


class EditBody(BaseModel):
    guest_id: str
    type: Literal["add", "remove", "swap", "move"]
    element_id: str
    to_element_id: str | None = None
    to_slot: str | None = None
    bet_axis: int = Field(ge=0, le=7)
    rationale: str | None = Field(default=None, max_length=140)
    version_id: str | None = None  # deck mode: optimistic lock


class DeckBody(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    libraries: list[str] = ["smith1909"]
    guest_id: str | None = None
    nickname: str = Field(default="anon", max_length=24)


class ApprovedBody(BaseModel):
    guest_id: str
    approved_editors: str | list[str]


class ConfigBody(BaseModel):
    w_axes: float | None = None
    w_embed: float | None = None
    radius: float | None = None
    v_lo: float | None = None
    alpha: float | None = None
    w_synthetic: float | None = None


def _check_axes(axes: list[float]) -> None:
    if any(a < -3 or a > 3 for a in axes):
        raise HTTPException(422, "axes must be within -3..3")


def _room_or_404(code: str) -> dict:
    try:
        return R.load(store(), code)
    except R.RoomError as e:
        raise HTTPException(e.status, e.detail)


def _deck_or_404(code: str) -> dict:
    try:
        return engine().deck(code)
    except KeyError:
        raise HTTPException(404, "no such deck")


def _view(room: dict, guest_id: str | None) -> dict:
    eng = engine()
    room = R.tick(store(), room, on_reveal=eng.on_reveal, on_close=eng.on_close)
    return eng.guest_view(room, guest_id)


def _wrap(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except R.RoomError as e:
        raise HTTPException(e.status, e.detail)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except KeyError as e:
        raise HTTPException(404, f"unknown id {e}")


# ----------------------------------------------------------------------------- read-only
def lan_ip() -> str | None:
    """Best-effort LAN address of this machine, so a lobby opened on localhost can still print a join
    URL that phones on the same wifi can reach."""
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


@app.get("/api/health")
def health():
    eng = engine()
    return {"ok": True, "lan_ip": lan_ip(), "web_url": os.environ.get("PIXIE_WEB_URL") or None, "store": store().kind, "embed_backend": embed_backend(), "naming_backend": naming_backend(),
            **eng.counts(), "config": eng.cfg(), "planted": eng.planted, "playground": eng.deck_summary(eng.playground)}


@app.get("/api/libraries")
def libraries():
    return store().all("libraries")


@app.get("/api/libraries/{library_id}/elements")
def library_elements(library_id: str):
    eng = engine()
    return [eng.element_view(e["id"]) | {"historical_prior": e.get("historical_prior"), "attestations": e.get("attestations", [])}
            for e in eng.elem_by_id.values() if e.get("library_id") == library_id]


@app.get("/api/config")
def get_config():
    return engine().cfg()


@app.post("/api/config")
def set_config(body: ConfigBody):
    eng = engine()
    for k, v in body.model_dump(exclude_none=True).items():
        eng.config[k] = float(v)
    eng.save_config()
    return eng.cfg()


@app.get("/api/geometry")
def geometry():
    return engine().geometry()


@app.get("/api/grammar")
def grammar_playground(include_synthetic: bool = Query(default=True)):
    g = engine().grammar(engine().playground, include_synthetic=include_synthetic)
    return {k: v for k, v in g.items() if k != "by_id"}


# ----------------------------------------------------------------------------- decks
@app.get("/api/decks")
def decks():
    eng = engine()
    return [eng.deck_summary(d) for d in sorted(store().all("decks"), key=lambda d: d.get("created_at") or "")]


@app.post("/api/decks")
def create_deck(body: DeckBody):
    guest_id = body.guest_id or R.new_id("g_")
    deck = engine().new_deck(body.name, body.libraries, owner_id=guest_id, nickname=body.nickname.strip()[:24] or "anon")
    return {"guest_id": guest_id, "deck": engine().deck_home(deck)}


@app.post("/api/decks/{code}/join")
def join_deck(code: str, body: JoinBody):
    guest_id = body.guest_id or R.new_id("g_")
    deck = engine().join_deck(_deck_or_404(code), guest_id, body.nickname.strip()[:24] or "anon")
    return {"guest_id": guest_id, "deck": engine().deck_home(deck)}


@app.get("/api/decks/{code}")
def deck_home(code: str, include_synthetic: bool = Query(default=False)):
    return engine().deck_home(_deck_or_404(code), include_synthetic=include_synthetic)


@app.get("/api/decks/{code}/elements")
def deck_elements(code: str):
    return engine().picker(_deck_or_404(code))


@app.get("/api/decks/{code}/grammar")
def deck_grammar(code: str, include_synthetic: bool = Query(default=True)):
    g = engine().grammar(_deck_or_404(code), include_synthetic=include_synthetic)
    return {k: v for k, v in g.items() if k != "by_id"}


@app.get("/api/decks/{code}/bandwidth")
def deck_bandwidth(code: str):
    return engine().bandwidth(_deck_or_404(code))


@app.get("/api/decks/{code}/cards/{card_id}")
def deck_card(code: str, card_id: str):
    deck = _deck_or_404(code)
    card = store().get("cards", card_id)
    if card is None or card.get("deck_id") != deck["id"]:
        raise HTTPException(404, "no such card in this deck")
    return engine().chain(card)


# -- deck mode (T2): async relay ------------------------------------------------
@app.post("/api/decks/{code}/cards")
def deck_compose(code: str, body: ComposeBody):
    _check_axes(body.axes)
    eng = engine()
    deck = _deck_or_404(code)
    if not any(m["guest_id"] == body.guest_id for m in deck["members"]):
        raise HTTPException(403, "join the deck first")
    card, version = _wrap(eng.make_card, deck, body.guest_id, body.model_dump(), "deck")
    card["maker_nickname"] = next((m["nickname"] for m in deck["members"] if m["guest_id"] == body.guest_id), None)
    store().put("cards", card)
    store().put("versions", version)
    return eng.chain(card)


@app.get("/api/decks/{code}/read")
def deck_read_queue(code: str, guest_id: str | None = None):
    """The version with the fewest human readings among cards in `reading`, skipping ones this guest already read."""
    eng = engine()
    deck = _deck_or_404(code)
    if not deck.get("open_read", True) and not any(m["guest_id"] == guest_id for m in deck["members"]):
        raise HTTPException(403, "this deck is not open for reading")
    best = None
    for c in store().find("cards", deck_id=deck["id"], status="reading"):
        if c.get("synthetic"):
            continue
        v = store().get("versions", c["latest_version_id"])
        if v is None:
            continue
        rs = store().find("readings", version_id=v["id"])
        if guest_id and any(r.get("reader_id") == guest_id for r in rs) or c.get("maker_id") == guest_id:
            continue
        n_h = sum(1 for r in rs if not r.get("synthetic"))
        if best is None or n_h < best[0]:
            best = (n_h, c, v)
    if best is None:
        return {"empty": True}
    n_h, c, v = best
    return {"empty": False, "card_id": c["id"], "version": {"id": v["id"], "v": int(v["v"]), "elements": eng.version_elements_view(v)},
            "n_human_readings": n_h, "ready_threshold": deck.get("ready_threshold", 3)}


@app.post("/api/decks/{code}/cards/{card_id}/readings")
def deck_reading(code: str, card_id: str, body: ReadingBody):
    _check_axes(body.axes)
    eng = engine()
    deck = _deck_or_404(code)
    card = store().get("cards", card_id)
    if card is None or card["deck_id"] != deck["id"] or card.get("status") != "reading":
        raise HTTPException(409, "this card is not collecting readings")
    v = store().get("versions", card["latest_version_id"])
    if any(r.get("reader_id") == body.guest_id for r in store().find("readings", version_id=v["id"])):
        raise HTTPException(400, "you already read this version")
    doc = eng.make_reading(body.guest_id, body.model_dump())
    doc.update({"card_id": card["id"], "version_id": v["id"], "deck_id": deck["id"], "room_id": None, "round_id": None,
                "nickname": next((m["nickname"] for m in deck["members"] if m["guest_id"] == body.guest_id), "reader")})
    store().put("readings", doc)
    n_h = sum(1 for r in store().find("readings", version_id=v["id"]) if not r.get("synthetic"))
    if n_h >= deck.get("ready_threshold", 3):
        rs = eng.readings(version_id=v["id"])
        prev = eng.prev_version(v)
        res = eng.evaluate(card, v, rs, eng.readings(version_id=prev["id"]) if prev else [], deck.get("max_edits", 6))
        card["status"] = "landed" if res["landed"] else ("closed" if int(v["v"]) >= deck.get("max_edits", 6) else "open")
        if card["status"] in ("landed", "closed"):
            card["finished_at"] = R.iso(R.utcnow())
        store().put("cards", card)
    eng._grammar_cache.clear()
    return {"ok": True, "n_human_readings": n_h, "status": card["status"]}


@app.post("/api/decks/{code}/cards/{card_id}/edit")
def deck_edit(code: str, card_id: str, body: EditBody):
    eng = engine()
    deck = _deck_or_404(code)
    card = store().get("cards", card_id)
    if card is None or card["deck_id"] != deck["id"]:
        raise HTTPException(404, "no such card")
    if card.get("status") != "open":
        raise HTTPException(409, "this card is not open for an edit yet")
    approved = card.get("approved_editors", "*")
    members = {m["guest_id"] for m in deck["members"]}
    if body.guest_id not in members or (approved != "*" and body.guest_id not in approved):
        raise HTTPException(403, "the maker has not approved you as an editor")
    if body.version_id and body.version_id != card["latest_version_id"]:
        raise HTTPException(409, "someone edited first — read v+1")
    current = store().get("versions", card["latest_version_id"])
    version = _wrap(eng.make_edit, deck, card, current, body.guest_id, body.model_dump())
    version["edit"]["editor_nickname"] = next((m["nickname"] for m in deck["members"] if m["guest_id"] == body.guest_id), None)
    store().put("versions", version)
    card["latest_version_id"] = version["id"]
    card["n_versions"] = int(version["v"]) + 1
    card["status"] = "reading"
    if body.guest_id not in card.get("encoder_ids", []):
        card.setdefault("encoder_ids", []).append(body.guest_id)
    store().put("cards", card)
    return eng.chain(card)


@app.post("/api/decks/{code}/cards/{card_id}/approved_editors")
def deck_approved(code: str, card_id: str, body: ApprovedBody):
    deck = _deck_or_404(code)
    card = store().get("cards", card_id)
    if card is None or card["deck_id"] != deck["id"]:
        raise HTTPException(404, "no such card")
    if card["maker_id"] != body.guest_id:
        raise HTTPException(403, "only the maker decides who may edit their card")
    card["approved_editors"] = body.approved_editors if body.approved_editors == "*" else list(body.approved_editors)
    store().put("cards", card)
    return engine().chain(card)


# ----------------------------------------------------------------------------- rooms (the relay)
@app.post("/api/rooms")
def create_room(body: JoinBody):
    deck = _deck_or_404(body.deck_code or "PLAY")
    guest_id, room = _wrap(R.create_room, store(), deck, body.nickname, body.guest_id)
    return {"guest_id": guest_id, "room": _view(room, guest_id)}


@app.post("/api/rooms/{code}/join")
def join_room(code: str, body: JoinBody):
    guest_id, room = _wrap(R.join_room, store(), code, body.nickname, body.guest_id)
    return {"guest_id": guest_id, "room": _view(room, guest_id)}


@app.get("/api/rooms/{code}")
def get_room(code: str, guest_id: str | None = None):
    return _view(_room_or_404(code), guest_id)


@app.get("/api/rooms/{code}/chains")
def room_chains(code: str):
    room = _room_or_404(code)
    return engine().room_chains(room)


@app.post("/api/rooms/{code}/start")
def start(code: str, body: GuestBody):
    room = _wrap(R.start, store(), _room_or_404(code), body.guest_id)
    return _view(room, body.guest_id)


@app.post("/api/rooms/{code}/compose")
def compose(code: str, body: ComposeBody):
    _check_axes(body.axes)
    eng = engine()
    room = _room_or_404(code)
    room = R.tick(store(), room, on_reveal=eng.on_reveal, on_close=eng.on_close)
    deck = store().get("decks", room["deck_id"]) or eng.playground
    card, version = _wrap(eng.make_card, deck, body.guest_id, body.model_dump(), "room")
    room = _wrap(R.compose, store(), room, body.guest_id, card, version)
    return _view(room, body.guest_id)


@app.post("/api/rooms/{code}/reading")
def reading(code: str, body: ReadingBody):
    _check_axes(body.axes)
    eng = engine()
    room = _room_or_404(code)
    room = R.tick(store(), room, on_reveal=eng.on_reveal, on_close=eng.on_close)
    doc = eng.make_reading(body.guest_id, body.model_dump())
    room = _wrap(R.submit_reading, store(), room, body.guest_id, doc, eng.on_reveal)
    return _view(room, body.guest_id)


@app.post("/api/rooms/{code}/edit")
def edit(code: str, body: EditBody):
    eng = engine()
    room = _room_or_404(code)
    room = R.tick(store(), room, on_reveal=eng.on_reveal, on_close=eng.on_close)
    rnd = room.get("round")
    if room["phase"] != "edit" or not rnd:
        raise HTTPException(400, "not waiting for an edit")
    deck = store().get("decks", room["deck_id"]) or eng.playground
    card = store().get("cards", rnd["card_id"])
    current = store().get("versions", rnd["version_id"])
    version = _wrap(eng.make_edit, deck, card, current, body.guest_id, body.model_dump())
    room = _wrap(R.submit_edit, store(), room, body.guest_id, version)
    return _view(room, body.guest_id)


@app.post("/api/rooms/{code}/continue")
def continue_(code: str, body: GuestBody):
    eng = engine()
    room = _wrap(R.continue_reveal, store(), _room_or_404(code), body.guest_id, eng.on_reveal, eng.on_close)
    return _view(room, body.guest_id)


@app.post("/api/rooms/{code}/replay")
def replay(code: str, body: GuestBody):
    eng = engine()
    room = _room_or_404(code)
    room = R.tick(store(), room, on_reveal=eng.on_reveal, on_close=eng.on_close)
    script = _wrap(eng.replay_script, room)
    room = _wrap(R.start_replay, store(), room, body.guest_id, script)
    return _view(room, body.guest_id)


@app.post("/api/rooms/{code}/replay/end")
def replay_end(code: str, body: GuestBody):
    room = _wrap(R.end_replay, store(), _room_or_404(code), body.guest_id)
    return _view(room, body.guest_id)

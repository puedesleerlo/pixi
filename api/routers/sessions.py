"""Live sessions (spec §11 Sessions). Presence and state via SSE with polling fallback."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth import current_user, require_user
from models import Deck, User
from routers.deps import deck_or_404, jobs, store, viewable_deck
from service import sessions as S
from service.permissions import can_host_session, can_join_session_as_reader, require_view, role_in_deck

router = APIRouter(prefix="/api", tags=["sessions"])


class CreateSession(BaseModel):
    mode: str = "relay"
    nickname: str = Field(default="host", max_length=24)
    settings: dict | None = None


class JoinBody(BaseModel):
    code: str = Field(min_length=4, max_length=4)
    nickname: str = Field(default="anon", max_length=24)


class ChooseBody(BaseModel):
    card_id: str


class SubmitBody(BaseModel):
    axes: list[float] = Field(min_length=8, max_length=8)
    free_text: str | None = Field(default=None, max_length=140)
    latency_ms: int | None = None


class EditBody(BaseModel):
    op: str
    symbol_id: str | None = None
    to_symbol_id: str | None = None
    placement: str | None = None
    region: dict | None = None
    bet_axis: int | None = Field(default=None, ge=0, le=7)
    rationale: str | None = Field(default=None, max_length=140)
    how_text: str | None = None


def _wrap(fn, *a, **k):
    try:
        return fn(*a, **k)
    except S.SessionError as e:
        raise HTTPException(e.status, {"code": "session", "detail": e.detail})


def _session_and_deck(sid: str) -> tuple[dict, Deck]:
    s = _wrap(S.load, store(), sid)
    return s, deck_or_404(s["deck_id"])


def _embed_fn():
    try:
        from pixie.embed import embed

        return embed
    except Exception:
        return None


@router.post("/decks/{deck_id}/sessions")
def create_session(body: CreateSession, deck: Deck = Depends(viewable_deck), user: User = Depends(require_user)):
    if not can_host_session(store(), deck, user):
        raise HTTPException(403, {"code": "role_required", "detail": "members can host sessions"})
    s = _wrap(S.create, store(), deck.to_doc(), user.id, body.nickname or user.name, body.mode, body.settings)
    return S.view(store(), deck.to_doc(), s, user.id)


@router.post("/sessions/join")
def join_session(body: JoinBody, user: User = Depends(require_user)):
    s = _wrap(S.by_code, store(), body.code)
    deck = deck_or_404(s["deck_id"])
    require_view(store(), deck, user)
    if user.is_guest and not can_join_session_as_reader(store(), deck, user, s["settings"].get("guests_allowed", True)):
        raise HTTPException(403, {"code": "role_required", "detail": "guests are not allowed here"})
    s = _wrap(S.join, store(), s, user.id, body.nickname or user.name, user.is_guest)
    return S.view(store(), deck.to_doc(), s, user.id)


@router.get("/sessions/{sid}")
def get_session(sid: str, user: User | None = Depends(current_user)):
    s, deck = _session_and_deck(sid)
    require_view(store(), deck, user)
    return S.view(store(), deck.to_doc(), s, user.id if user else None)


@router.post("/sessions/{sid}/start")
def start(sid: str, user: User = Depends(require_user)):
    s, deck = _session_and_deck(sid)
    s = _wrap(S.start, store(), s, user.id)
    return S.view(store(), deck.to_doc(), s, user.id)


@router.post("/sessions/{sid}/choose")
def choose(sid: str, body: ChooseBody, user: User = Depends(require_user)):
    s, deck = _session_and_deck(sid)
    card = store().get("cards", body.card_id)
    if card is None:
        raise HTTPException(404, {"code": "not_found", "detail": "no such card"})
    s = _wrap(S.choose_card, store(), deck.to_doc(), s, user.id, card)
    return S.view(store(), deck.to_doc(), s, user.id)


@router.post("/sessions/{sid}/rounds/{rid}/submit")
def submit(sid: str, rid: str, body: SubmitBody, user: User = Depends(require_user)):
    s, deck = _session_and_deck(sid)
    if s.get("current_round_id") != rid:
        raise HTTPException(409, {"code": "round_stale", "detail": "that round is over"})
    s = _wrap(S.submit_reading, store(), deck.to_doc(), s, user.id, body.model_dump(), _embed_fn())
    return S.view(store(), deck.to_doc(), s, user.id)


@router.post("/sessions/{sid}/advance")
def advance(sid: str, user: User = Depends(require_user)):
    s, deck = _session_and_deck(sid)
    s = _wrap(S.advance, store(), deck.to_doc(), s, user.id)
    return S.view(store(), deck.to_doc(), s, user.id)


@router.post("/sessions/{sid}/end")
def end(sid: str, user: User = Depends(require_user)):
    s, deck = _session_and_deck(sid)
    s = _wrap(S.end, store(), s, user.id)
    return S.view(store(), deck.to_doc(), s, user.id)


@router.post("/sessions/{sid}/edit")
def live_edit(sid: str, body: EditBody, user: User = Depends(require_user)):
    """One op by the current editor → imaging job (live) → the new version is attached when chosen.
    Uses service.cards.start_edit when available (slice 6); until then returns 501."""
    s, deck = _session_and_deck(sid)
    if s["state"] != "edit" or s.get("current_editor_id") != user.id:
        raise HTTPException(403, {"code": "role_required", "detail": "not your edit turn"})
    try:
        from service import cards as cards_svc
    except ImportError:
        raise HTTPException(501, {"code": "not_implemented", "detail": "live edits arrive with slice 6"})
    card = store().get("cards", s["current_card_id"])
    # mark the session `generating` first: an inline worker finishes the job (and attaches the version) before start_edit returns
    s = _wrap(S.begin_edit, store(), s, user.id, None)
    try:
        res = cards_svc.start_edit(store(), jobs(), deck, card, user, {**body.model_dump(), "base_version_id": s["current_version_id"], "n": 1,
                                                                         "session_id": s["id"], "auto_choose": True})
    except Exception as e:
        cur = S.load(store(), s["id"])
        if cur.get("state") == "generating":  # give the turn back
            cur["state"] = "edit"
            cur["pending_job_id"] = None
            store().put("sessions", cur)
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(422 if isinstance(e, ValueError) else 500, {"code": "edit_failed", "detail": str(e)})
    job = res.get("job") if isinstance(res, dict) and "job" in res else res
    job_id = (job or {}).get("id") if isinstance(job, dict) else None
    cur = S.load(store(), s["id"])
    if cur.get("state") == "generating" and job_id:
        cur["pending_job_id"] = job_id
        store().put("sessions", cur)
    return {"job": job, "session": S.view(store(), deck.to_doc(), cur, user.id)}


@router.get("/sessions/{sid}/events")
async def events(sid: str, user: User | None = Depends(current_user)):
    s, deck = _session_and_deck(sid)
    require_view(store(), deck, user)
    uid = user.id if user else None

    async def gen():
        last = None
        beats = 0
        while True:
            try:
                cur = S.load(store(), sid)
                view = S.view(store(), deck.to_doc(), cur, uid)
                key = (view["state"], view.get("round_ends_at"), len(view["players"]), (view.get("round") or {}).get("n_submitted"), view.get("current_version_id"))
                if key != last:
                    last = key
                    yield f"event: session.state\ndata: {json.dumps(view)}\n\n"
                    yield f"event: session.presence\ndata: {json.dumps({'players': view['players']})}\n\n"
                if view["state"] == "ended":
                    break
            except Exception as e:  # keep the stream alive
                yield f": error {type(e).__name__}\n\n"
            beats += 1
            if beats % 30 == 0:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

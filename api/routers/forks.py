"""Forks and upstream proposals (spec §11 Forks & upstream) on top of service/forks.py."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_user
from models import Deck, User
from routers.deps import deck_or_404, store, viewable_deck
from service import activity, forks
from service.permissions import require_role

router = APIRouter(prefix="/api", tags=["forks"])


class ProposalBody(BaseModel):
    kind: str
    version_id: str | None = None
    symbol_id: str | None = None
    note: str = Field(default="", max_length=280)


class DecisionBody(BaseModel):
    action: str  # accept | decline
    note: str | None = Field(default=None, max_length=280)


def _wrap(fn, *a, **k):
    try:
        return fn(*a, **k)
    except forks.ForkError as e:
        raise HTTPException(e.status, {"code": "fork", "detail": e.detail})


@router.get("/decks/{deck_id}/lineage")
def lineage(deck: Deck = Depends(viewable_deck)):
    return forks.lineage(store(), deck.to_doc())


@router.post("/decks/{deck_id}/upstream-proposals")
def propose(deck_id: str, body: ProposalBody, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    require_role(store(), deck, user, "curator")
    ref = body.version_id if body.kind == "version" else body.symbol_id
    if not ref:
        raise HTTPException(422, {"code": "validation", "detail": "version_id or symbol_id required"})
    p = _wrap(forks.propose_upstream, store(), deck.to_doc(), user.id, body.kind, ref, body.note)
    try:
        activity.log(store(), p["to_deck_id"], user.id, "upstream_proposal", {"proposal_id": p["id"], "from_deck_id": deck.id})
    except Exception:
        pass
    return p


@router.get("/decks/{deck_id}/upstream-proposals")
def list_proposals(direction: str = "inbox", deck: Deck = Depends(viewable_deck)):
    if direction == "outbox":
        return store().find("upstream_proposals", from_deck_id=deck.id)
    return store().find("upstream_proposals", to_deck_id=deck.id)


@router.patch("/upstream-proposals/{pid}")
def decide(pid: str, body: DecisionBody, user: User = Depends(require_user)):
    p = store().get("upstream_proposals", pid)
    if p is None:
        raise HTTPException(404, {"code": "not_found", "detail": "no such proposal"})
    deck = deck_or_404(p["to_deck_id"])
    require_role(store(), deck, user, "curator")
    if body.action not in ("accept", "decline"):
        raise HTTPException(422, {"code": "validation", "detail": "action must be accept or decline"})
    return _wrap(forks.decide_upstream, store(), p, user.id, body.action == "accept", body.note)


@router.post("/decks/{deck_id}/sync-from-parent")
def sync(deck_id: str, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    require_role(store(), deck, user, "curator")
    return _wrap(forks.sync_from_parent, store(), deck.to_doc(), user.id)

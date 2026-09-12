from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import current_user, require_user
from models import Deck, ImportBody, MergeBody, ProposalCreate, ProposalDecision, SymbolDraft, SymbolPatch, User
from routers.deps import deck_or_404, store, storage, viewable_deck
from service import symbols as sym
from service.permissions import can_manage_symbols, can_propose_symbol, require_role, require_view, role_in_deck

router = APIRouter(prefix="/api", tags=["symbols"])


def _deck_of_symbol(sid: str):
    s = sym.get_symbol(store(), sid)
    return s, deck_or_404(s.deck_id)


@router.get("/decks/{deck_id}/symbols")
def list_symbols(status: str | None = Query(default="active"), deck: Deck = Depends(viewable_deck)):
    st = None if status in (None, "", "all") else status
    return [s.model_dump() for s in sym.list_symbols(store(), deck.id, st)]


@router.post("/decks/{deck_id}/symbols", status_code=201)
def add_symbol(deck_id: str, body: SymbolDraft, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    if not can_manage_symbols(store(), deck, user):
        raise HTTPException(403, {"code": "role_required", "detail": "curators add symbols; members propose them"})
    return sym.create_symbol(store(), storage(), deck, user, body).model_dump()


@router.get("/symbols/{sid}")
def symbol_detail(sid: str, user: User | None = Depends(current_user)):
    s, deck = _deck_of_symbol(sid)
    require_view(store(), deck, user)
    d = s.model_dump()
    d["cards"] = sym.cards_using(store(), deck.id, s.id)
    d["proposals"] = [p for p in store().find("symbol_proposals", deck_id=deck.id) if p.get("symbol_id") == s.id]
    return d


@router.patch("/symbols/{sid}")
def patch_symbol(sid: str, body: SymbolPatch, user: User = Depends(require_user)):
    s, deck = _deck_of_symbol(sid)
    require_role(store(), deck, user, "curator")
    return sym.patch_symbol(store(), storage(), deck, s, body, user).model_dump()


@router.post("/symbols/{sid}/merge")
def merge(sid: str, body: MergeBody, user: User = Depends(require_user)):
    s, deck = _deck_of_symbol(sid)
    require_role(store(), deck, user, "curator")
    into = sym.get_symbol(store(), body.into_symbol_id)
    return sym.merge_symbol(store(), deck, s, into, user)


@router.post("/symbols/{sid}/retire")
def retire(sid: str, user: User = Depends(require_user)):
    s, deck = _deck_of_symbol(sid)
    require_role(store(), deck, user, "curator")
    return sym.retire_symbol(store(), deck, s, user).model_dump()


@router.post("/decks/{deck_id}/symbols/import", status_code=201)
def import_symbols(deck_id: str, body: ImportBody, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    require_role(store(), deck, user, "curator")
    return [s.model_dump() for s in sym.import_from_base(store(), storage(), deck, body.base_deck_slug, body.symbol_keys, user)]


@router.get("/decks/{deck_id}/symbol-proposals")
def list_proposals(deck_id: str, status: str | None = None, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    role = require_role(store(), deck, user, "member")
    rows = sym.list_proposals(store(), deck.id, status)
    if role == "member":
        rows = [p for p in rows if p.get("proposed_by") == user.id]
    return rows


@router.post("/decks/{deck_id}/symbol-proposals", status_code=201)
def propose(deck_id: str, body: ProposalCreate, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    if not can_propose_symbol(store(), deck, user):
        raise HTTPException(403, {"code": "role_required", "detail": "members propose symbols"})
    return sym.propose(store(), deck, user, body.symbol_draft, body.note).model_dump()


@router.patch("/symbol-proposals/{pid}")
def decide(pid: str, body: ProposalDecision, user: User = Depends(require_user)):
    p = store().get("symbol_proposals", pid)
    if p is None:
        raise HTTPException(404, {"code": "not_found", "detail": "no such proposal"})
    deck = deck_or_404(p["deck_id"])
    require_role(store(), deck, user, "curator")
    return sym.decide_proposal(store(), storage(), deck, pid, user, body.action, body.decision_note).model_dump()

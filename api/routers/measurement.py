"""Per-deck grammar, coherence and transmission (spec §11 Decks: /grammar, /coherence)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from models import Deck
from routers.deps import store, viewable_deck
from service import coherence, decks as decks_svc, measure

router = APIRouter(prefix="/api", tags=["measurement"])


@router.get("/decks/{deck_id}/grammar")
def grammar(include_synthetic: bool = Query(default=True), deck: Deck = Depends(viewable_deck)):
    g = measure.grammar(store(), deck.id, include_synthetic=include_synthetic)
    return {k: v for k, v in g.items() if k != "by_id"}


@router.get("/decks/{deck_id}/coherence")
def coherence_dashboard(deck: Deck = Depends(viewable_deck)):
    positions = None
    try:
        positions = [p.model_dump() for p in decks_svc.structure(deck.structure_template_id).positions]
    except Exception:
        positions = None
    return coherence.dashboard(store(), deck.to_doc(), positions)


@router.get("/decks/{deck_id}/transmission")
def transmission(deck: Deck = Depends(viewable_deck)):
    return measure.transmission(store(), deck.to_doc())


@router.get("/decks/{deck_id}/planted")
def planted(deck: Deck = Depends(viewable_deck)):
    from service import seeds

    meta = store().get("meta", "seeds") or {}
    if meta.get("deck_id") != deck.id:
        return None
    return meta.get("planted")

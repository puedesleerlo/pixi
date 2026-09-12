"""Readings (spec §11 Readings): the async queue, submit, reveal, verdict."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user, require_user
from models import Deck, User
from routers.deps import store, viewable_deck
from service import measure, readings as RD
from service.permissions import can_read_card, is_maker, require_view, role_in_deck

router = APIRouter(prefix="/api", tags=["readings"])


class ReadingBody(BaseModel):
    axes: list[float] = Field(min_length=8, max_length=8)
    free_text: str | None = Field(default=None, max_length=140)
    latency_ms: int | None = None


def _embed_fn():
    try:
        from pixie.embed import embed

        return embed
    except Exception:
        return None


def _version_or_404(vid: str) -> dict:
    v = store().get("versions", vid)
    if v is None:
        raise HTTPException(404, {"code": "not_found", "detail": "no such version"})
    return v


def _deck_of(version: dict) -> Deck:
    from service import decks as decks_svc

    return decks_svc.get_deck(store(), version["deck_id"])


def _is_encoder(card: dict, deck: Deck, user: User | None) -> bool:
    if user is None:
        return False
    if card.get("maker_id") == user.id or user.id in (card.get("encoder_ids") or []):
        return True
    return role_in_deck(store(), deck, user) in ("curator", "owner")


@router.get("/decks/{deck_id}/read/next")
def read_next(deck: Deck = Depends(viewable_deck), user: User | None = Depends(current_user)):
    if not can_read_card(store(), deck, user):
        raise HTTPException(403, {"code": "role_required", "detail": "this deck does not allow guest readers"})
    item = RD.next_to_read(store(), deck.to_doc(), user.id if user else None)
    return {"empty": True} if item is None else {"empty": False, **item}


@router.post("/versions/{vid}/readings")
def submit_reading(vid: str, body: ReadingBody, user: User = Depends(require_user)):
    version = _version_or_404(vid)
    deck = _deck_of(version)
    require_view(store(), deck, user)
    if not can_read_card(store(), deck, user):
        raise HTTPException(403, {"code": "role_required", "detail": "this deck does not allow guest readers"})
    try:
        reading, card = RD.submit(store(), deck.to_doc(), version, user.id, body.model_dump(), embed_fn=_embed_fn(), nickname=user.name)
    except RD.ReadingError as e:
        raise HTTPException(e.status, {"code": "reading_rejected", "detail": e.detail})
    return {"reading_id": reading["id"], "card_status": card.get("status"),
            "reveal": measure.reveal(store(), deck.to_doc(), card, version, user.id, encoder=False)}


@router.get("/versions/{vid}/reveal")
def reveal(vid: str, user: User | None = Depends(current_user)):
    version = _version_or_404(vid)
    deck = _deck_of(version)
    require_view(store(), deck, user)
    card = store().get("cards", version["card_id"])
    return measure.reveal(store(), deck.to_doc(), card, version, user.id if user else None, encoder=_is_encoder(card, deck, user))


@router.get("/versions/{vid}/verdict")
def verdict(vid: str, user: User | None = Depends(current_user)):
    version = _version_or_404(vid)
    deck = _deck_of(version)
    require_view(store(), deck, user)
    return measure.verdict(store(), deck.id, version)


@router.get("/versions/{vid}")
def get_version(vid: str, user: User | None = Depends(current_user)):
    version = _version_or_404(vid)
    deck = _deck_of(version)
    require_view(store(), deck, user)
    return version

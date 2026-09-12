"""Shared dependencies: store, storage, job runner, deck resolution."""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Query, Request

from auth import current_user
from models import Deck, User
from service import decks as decks_svc
from service.permissions import require_view

state: dict[str, Any] = {}


def store():
    return state["store"]


def storage():
    return state["storage"]


def jobs():
    return state["jobs"]


def deck_or_404(deck_id: str) -> Deck:
    return decks_svc.get_deck(store(), deck_id)


def viewable_deck(deck_id: str, user: User | None = Depends(current_user), share_token: str | None = Query(default=None)) -> Deck:
    deck = deck_or_404(deck_id)
    require_view(store(), deck, user, share_token)
    return deck

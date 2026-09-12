"""Export ZIP and print PDF (spec §5.11)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import require_user
from models import Deck, User
from routers.deps import deck_or_404, jobs, store
from service import export as _export  # noqa: F401  (registers the job handler)
from service.permissions import require_role

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/decks/{deck_id}/export")
def export_zip(deck_id: str, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    require_role(store(), deck, user, "member")
    return {"job": jobs().enqueue("export", {"deck_id": deck.id, "kind": "zip"}, created_by=user.id, deck_id=deck.id)}


@router.get("/decks/{deck_id}/print")
def export_pdf(deck_id: str, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    require_role(store(), deck, user, "member")
    return {"job": jobs().enqueue("export", {"deck_id": deck.id, "kind": "pdf"}, created_by=user.id, deck_id=deck.id)}

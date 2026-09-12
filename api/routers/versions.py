"""Versions (spec §11 Cards): choose a candidate, restore, compare, list candidates."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user, require_user
from models import Deck, User
from routers.deps import deck_or_404, storage, store
from service import cards as C
from service.permissions import at_least, require_view, role_in_deck

router = APIRouter(prefix="/api", tags=["versions"])


class ChooseBody(BaseModel):
    index: int = Field(ge=0, le=15)


class RestoreBody(BaseModel):
    note: str = Field(default="", max_length=140)


def _version_card_deck(vid: str) -> tuple[dict, dict, Deck]:
    version = C.get_version(store(), vid)
    card = C.get_card(store(), version["card_id"])
    return version, card, deck_or_404(version["deck_id"])


@router.post("/versions/{vid}/choose")
def choose(vid: str, body: ChooseBody, user: User = Depends(require_user)):
    version, card, deck = _version_card_deck(vid)
    require_view(store(), deck, user)
    version = C.choose_candidate(store(), storage(), deck, card, version, user, body.index)
    card = C.get_card(store(), card["id"])
    return {"version": {k: v for k, v in version.items() if k != "how"} | {"how": {k: v for k, v in version["how"].items() if k != "candidates"}},
            "card": C.card_view(store(), storage(), deck, card, user)}


@router.get("/versions/{vid}/candidates")
def candidates(vid: str, user: User = Depends(require_user)):
    version, card, deck = _version_card_deck(vid)
    require_view(store(), deck, user)
    if version.get("created_by") != user.id and not at_least(role_in_deck(store(), deck, user), "curator"):
        raise HTTPException(403, {"code": "role_required", "detail": "candidates are visible to their creator and curators"})
    how = version.get("how") or {}
    return {"version_id": version["id"], "status": version.get("status", "chosen"), "chosen_index": how.get("chosen_index"),
            "op": how.get("op"), "mode": how.get("mode"), "prompt_full": how.get("prompt_full"), "provider": how.get("provider"), "model": how.get("model"),
            "retries": how.get("retries"), "fidelity_threshold": how.get("fidelity_threshold"), "expected_region": how.get("expected_region"),
            "counts_as_experiment": how.get("counts_as_experiment"), "safety": (version.get("checks") or {}).get("safety"),
            "safety_reason": (version.get("checks") or {}).get("safety_reason"), "candidates": C._public_candidates(storage(), how.get("candidates") or [])}


@router.post("/versions/{vid}/restore", status_code=201)
def restore(vid: str, body: RestoreBody, user: User = Depends(require_user)):
    version, card, deck = _version_card_deck(vid)
    require_view(store(), deck, user)
    nv = C.restore(store(), storage(), deck, card, version, user, body.note)
    return {"version": {k: v for k, v in nv.items() if k != "how"} | {"how": nv["how"]}, "card": C.card_view(store(), storage(), deck, C.get_card(store(), card["id"]), user)}


@router.get("/versions/{vid}/compare/{vid2}")
def compare(vid: str, vid2: str, user: User | None = Depends(current_user)):
    v1, card, deck = _version_card_deck(vid)
    require_view(store(), deck, user)
    v2 = C.get_version(store(), vid2)
    if v2.get("card_id") != card["id"]:
        raise HTTPException(422, {"code": "validation", "detail": "versions belong to different cards"})
    return C.compare(store(), storage(), v1, v2)

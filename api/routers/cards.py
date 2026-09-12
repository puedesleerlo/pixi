"""Cards (spec §11 Cards, Reinterpret): CRUD, edit requests, generate and edit jobs, branches, listing."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import current_user, require_user
from models import Deck, User
from routers.deps import deck_or_404, jobs, storage, store, viewable_deck
from service import cards as C
from service.permissions import at_least, can_create_card, require_role, require_view, role_in_deck

router = APIRouter(prefix="/api", tags=["cards"])


# ----------------------------------------------------------------------------- bodies
class IntentBody(BaseModel):
    statement: str = Field(min_length=1, max_length=140)
    axes: list[float] = Field(min_length=8, max_length=8)


class CardCreate(BaseModel):
    position_key: str | None = None
    title: str | None = Field(default=None, max_length=80)
    intent: IntentBody | None = None
    approved_editors: str | list[str] | None = None
    tags: list[str] = []


class CardPatch(BaseModel):
    title: str | None = Field(default=None, max_length=80)
    intent: IntentBody | None = None
    approved_editors: str | list[str] | None = None
    tags: list[str] | None = None


class ReferenceBody(BaseModel):
    base_card_id: str | None = None
    card_id: str | None = None
    version_id: str | None = None
    image_base64: str | None = None


class GenerateBody(BaseModel):
    mode: Literal["prompt", "reference", "variation", "upload"] = "prompt"
    prompt_user: str = Field(default="", max_length=600)
    symbols: list[str | dict] = []          # ids, or {symbol_id, placement?} as the web sends
    n: int | None = Field(default=None, ge=1, le=4)
    seed: int | None = None
    reference: ReferenceBody | None = None
    reference_image_url: str | None = None  # web alias for reference.image_url
    strength: float | None = Field(default=None, ge=0.3, le=0.8)
    image_base64: str | None = None
    upload_data_url: str | None = None      # web alias: data:image/png;base64,…
    rights_attested: bool = False
    branch_key: str | None = None

    def normalised(self) -> dict:
        d = self.model_dump()
        placements = {}
        ids = []
        for x in self.symbols:
            if isinstance(x, dict):
                sid = x.get("symbol_id") or x.get("id")
                if sid:
                    ids.append(sid)
                    if x.get("placement"):
                        placements[sid] = x["placement"]
            elif x:
                ids.append(x)
        d["symbols"] = ids
        d["placements"] = placements
        if self.reference_image_url and not d.get("reference"):
            d["reference"] = {"image_url": self.reference_image_url}
        if self.upload_data_url and not self.image_base64:
            d["image_base64"] = self.upload_data_url.split(",", 1)[-1]
        return d


class RegionBody(BaseModel):
    x: float
    y: float
    w: float
    h: float


class EditBody(BaseModel):
    op: Literal["add", "remove", "replace", "emphasize", "deemphasize", "reposition", "cosmetic"]
    symbol_id: str | None = None
    to_symbol_id: str | None = None
    region: RegionBody | None = None
    placement: str | None = None
    target_region: RegionBody | None = None
    target_placement: str | None = None
    how_text: str | None = Field(default=None, max_length=300)
    rationale: str = Field(default="", max_length=140)
    bet_axis: int | None = Field(default=None, ge=0, le=7)
    n: int | None = Field(default=None, ge=1, le=4)
    seed: int | None = None
    strength: float | None = None
    base_version_id: str | None = None
    branch_key: str | None = None
    auto_choose: bool = False
    session_id: str | None = None


class EditRequestBody(BaseModel):
    note: str = Field(default="", max_length=140)


class EditRequestDecision(BaseModel):
    action: Literal["approve", "decline"]


class BranchBody(BaseModel):
    from_version_id: str | None = None
    branch_key: str | None = None


class ReinterpretBody(BaseModel):
    base_deck_slug: str | None = None
    positions: list[str] | None = None
    group: str | None = None
    assign_makers: dict[str, str] | None = None
    n: int | None = Field(default=None, ge=1, le=2)


# ----------------------------------------------------------------------------- helpers
def _card_and_deck(cid: str) -> tuple[dict, Deck]:
    card = C.get_card(store(), cid)
    return card, deck_or_404(card["deck_id"])


def _body(b: BaseModel) -> dict:
    return b.model_dump(exclude_none=True)


# ----------------------------------------------------------------------------- listing & create
@router.get("/decks/{deck_id}/cards")
def list_cards(deck: Deck = Depends(viewable_deck), user: User | None = Depends(current_user), status: str | None = Query(default=None),
               mine: bool = Query(default=False), needs_readings: bool = Query(default=False), open_for_edit: bool = Query(default=False),
               contested: bool = Query(default=False), off_style: bool = Query(default=False)):
    return C.list_cards(store(), deck, user, {"status": status, "mine": mine, "needs_readings": needs_readings, "open_for_edit": open_for_edit,
                                              "contested": contested, "off_style": off_style})


@router.post("/decks/{deck_id}/cards", status_code=201)
def create_card(deck_id: str, body: CardCreate, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    require_view(store(), deck, user)
    if not can_create_card(store(), deck, user):
        raise HTTPException(403, {"code": "role_required", "detail": "this deck lets curators create cards" if deck.settings.who_can_create_cards == "curators" else "members create cards"})
    card = C.create_card(store(), deck, user, _body(body))
    return C.card_view(store(), storage(), deck, card, user)


@router.get("/cards/{cid}")
def get_card(cid: str, user: User | None = Depends(current_user), share_token: str | None = Query(default=None)):
    card, deck = _card_and_deck(cid)
    if share_token and card.get("share_token") == share_token:
        pass
    else:
        require_view(store(), deck, user, share_token)
    return C.card_view(store(), storage(), deck, card, user)


@router.patch("/cards/{cid}")
def patch_card(cid: str, body: CardPatch, user: User = Depends(require_user)):
    card, deck = _card_and_deck(cid)
    require_view(store(), deck, user)
    card = C.update_card(store(), deck, card, user, body.model_dump(exclude_unset=True))
    return C.card_view(store(), storage(), deck, card, user)


@router.post("/cards/{cid}/open")
def open_for_edits(cid: str, user: User = Depends(require_user)):
    """Maker or curator: open a card for edits before the reading threshold (needs ≥ 1 reading)."""
    from service import readings as _rd
    from service.permissions import role_in_deck

    card, deck = _card_and_deck(cid)
    require_view(store(), deck, user)
    curator = role_in_deck(store(), deck, user) in ("curator", "owner")
    try:
        card = _rd.open_for_edits(store(), deck.to_doc() if hasattr(deck, "to_doc") else deck, card, user.id, curator)
    except _rd.ReadingError as e:
        raise HTTPException(e.status, {"code": "open_refused", "detail": e.detail})
    return C.card_view(store(), storage(), deck, card, user)


@router.post("/cards/{cid}/archive")
def archive(cid: str, user: User = Depends(require_user)):
    card, deck = _card_and_deck(cid)
    require_view(store(), deck, user)
    card = C.archive_card(store(), deck, card, user)
    return C.card_view(store(), storage(), deck, card, user)


# ----------------------------------------------------------------------------- edit requests (§5.9)
@router.post("/cards/{cid}/edit-requests", status_code=201)
def request_edit(cid: str, body: EditRequestBody, user: User = Depends(require_user)):
    card, deck = _card_and_deck(cid)
    require_role(store(), deck, user, "member")
    return C.create_edit_request(store(), deck, card, user, body.note)


@router.get("/cards/{cid}/edit-requests")
def list_edit_requests(cid: str, user: User = Depends(require_user)):
    card, deck = _card_and_deck(cid)
    require_view(store(), deck, user)
    reqs = card.get("edit_requests") or []
    if card.get("maker_id") == user.id or at_least(role_in_deck(store(), deck, user), "curator"):
        return reqs
    return [r for r in reqs if r.get("user_id") == user.id]


@router.patch("/cards/{cid}/edit-requests/{rid}")
def decide_edit_request(cid: str, rid: str, body: EditRequestDecision, user: User = Depends(require_user)):
    card, deck = _card_and_deck(cid)
    require_view(store(), deck, user)
    return C.decide_edit_request(store(), deck, card, user, rid, body.action)


# ----------------------------------------------------------------------------- versions & jobs
@router.get("/cards/{cid}/versions")
def versions(cid: str, user: User | None = Depends(current_user)):
    card, deck = _card_and_deck(cid)
    require_view(store(), deck, user)
    return C.list_versions(store(), card)


@router.post("/cards/{cid}/generate", status_code=202)
def generate(cid: str, body: GenerateBody, user: User = Depends(require_user)):
    card, deck = _card_and_deck(cid)
    require_role(store(), deck, user, "member")
    payload: dict[str, Any] = {k: v for k, v in body.normalised().items() if v is not None}
    out = C.start_generate(store(), jobs(), storage(), deck, card, user, payload)
    if out.get("version") is not None:  # upload: no job
        return {"job": None, "version_id": out["version"]["id"], "card": C.card_view(store(), storage(), deck, C.get_card(store(), cid), user)}
    return out


@router.post("/cards/{cid}/edit", status_code=202)
def edit(cid: str, body: EditBody, user: User = Depends(require_user)):
    card, deck = _card_and_deck(cid)
    require_role(store(), deck, user, "member")
    payload = body.model_dump(exclude_none=True)
    return C.start_edit(store(), jobs(), deck, card, user, payload)


@router.post("/cards/{cid}/branches", status_code=201)
def branch(cid: str, body: BranchBody, user: User = Depends(require_user)):
    card, deck = _card_and_deck(cid)
    require_view(store(), deck, user)
    card = C.create_branch(store(), deck, card, user, body.from_version_id, body.branch_key)
    return {"card_id": card["id"], "branches": card.get("branches") or []}


@router.post("/decks/{deck_id}/reinterpret", status_code=202)
def reinterpret(deck_id: str, body: ReinterpretBody, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    require_role(store(), deck, user, "curator")
    return C.start_reinterpret(store(), jobs(), storage(), deck, user, body.model_dump(exclude_none=True))

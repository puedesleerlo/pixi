from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import current_user, require_account, require_user
from models import Deck, DeckCreate, DeckPatch, ForkBody, User
from routers.deps import deck_or_404, store, storage, viewable_deck
from service import activity, decks as decks_svc
from service.permissions import can_fork, require_role, require_view, role_in_deck

router = APIRouter(prefix="/api", tags=["decks"])


def deck_view(deck: Deck, user: User | None) -> dict:
    s = store()
    deck = decks_svc.recompute_stats(s, deck)
    d = deck.model_dump()
    d["your_role"] = role_in_deck(s, deck, user)
    if d["your_role"] not in ("owner", "curator"):
        d.pop("share_token", None)
    d["structure"] = decks_svc.structure(deck.structure_template_id).model_dump()
    return d


@router.get("/structures")
def list_structures():
    return [t.model_dump() for t in decks_svc.structures().values()]


@router.get("/decks")
def list_decks(visibility: str = Query(default="public"), sort: str = Query(default="recent"), limit: int = 50, user: User | None = Depends(current_user)):
    return [deck_view(d, user) for d in decks_svc.list_decks(store(), user, visibility, sort, limit)]


@router.post("/decks", status_code=201)
def create_deck(body: DeckCreate, user: User = Depends(require_account)):
    if body.origin.kind == "fork":
        src = decks_svc.get_deck(store(), body.origin.forked_from_deck_id or "")
        if not can_fork(store(), src, user):
            raise HTTPException(403, {"code": "role_required", "detail": "you cannot fork this deck"})
    deck = decks_svc.create_deck(store(), storage(), user, body)
    return deck_view(deck, user)


@router.get("/decks/{deck_id}")
def get_deck(deck: Deck = Depends(viewable_deck), user: User | None = Depends(current_user)):
    return deck_view(deck, user)


@router.patch("/decks/{deck_id}")
def patch_deck(deck_id: str, body: DeckPatch, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    role = require_role(store(), deck, user, "curator")
    return deck_view(decks_svc.update_deck(store(), deck, body, user, role), user)


@router.delete("/decks/{deck_id}")
def delete_deck(deck_id: str, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    require_role(store(), deck, user, "owner")
    decks_svc.delete_deck(store(), deck)
    return {"deleted": deck.id}


@router.post("/decks/{deck_id}/fork", status_code=201)
def fork(deck_id: str, body: ForkBody | None = None, user: User = Depends(require_account)):
    src = deck_or_404(deck_id)
    require_view(store(), src, user)
    if not can_fork(store(), src, user):
        raise HTTPException(403, {"code": "role_required", "detail": "forks are not allowed on this deck"})
    body = body or ForkBody()
    from service import forks as forks_svc
    try:
        deck_doc, _snap = forks_svc.fork(store(), src.to_doc(), user.id, body.name, body.visibility)
    except forks_svc.ForkError as e:  # type: ignore[attr-defined]
        raise HTTPException(getattr(e, "status", 403), {"code": "role_required", "detail": str(e)})
    activity.log(store(), src.id, user.id, "deck.forked", {"fork_deck_id": deck_doc["id"]})
    activity.log(store(), deck_doc["id"], user.id, "deck.created", {"origin": "fork", "from": src.id})
    from service.notifications import notify
    notify(store(), src.owner_id, "fork.created", f"{user.name} forked {src.name}", deck_id=src.id)
    return deck_view(Deck(**deck_doc), user)


@router.get("/decks/{deck_id}/activity")
def deck_activity(limit: int = 50, deck: Deck = Depends(viewable_deck)):
    s = store()
    users = {}
    out = []
    for a in activity.feed(s, deck.id, limit):
        uid = a.get("actor_id")
        if uid and uid not in users:
            u = s.get("users", uid) or {}
            users[uid] = u.get("name")
        out.append({**a, "actor_name": users.get(uid)})
    return out

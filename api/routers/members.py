from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth import current_user, require_account, require_user
from models import Deck, InvitationCreate, MemberAdd, MemberPatch, User
from routers.deps import deck_or_404, store, viewable_deck
from service import decks as decks_svc
from service.permissions import can_invite, can_manage_members, require_role

router = APIRouter(prefix="/api", tags=["members"])


@router.get("/decks/{deck_id}/members")
def list_members(deck: Deck = Depends(viewable_deck)):
    return decks_svc.list_members(store(), deck)


@router.post("/decks/{deck_id}/members", status_code=201)
def add_member(deck_id: str, body: MemberAdd, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    if not can_manage_members(store(), deck, user):
        raise HTTPException(403, {"code": "role_required", "detail": "only the owner manages members"})
    return decks_svc.add_member(store(), deck, user, body.user_id, body.email, body.role)


@router.patch("/decks/{deck_id}/members/{uid}")
def set_role(deck_id: str, uid: str, body: MemberPatch, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    if not can_manage_members(store(), deck, user):
        raise HTTPException(403, {"code": "role_required", "detail": "only the owner manages roles"})
    return decks_svc.set_role(store(), deck, user, uid, body.role)


@router.delete("/decks/{deck_id}/members/{uid}")
def remove_member(deck_id: str, uid: str, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    if not (can_manage_members(store(), deck, user) or uid == user.id):
        raise HTTPException(403, {"code": "role_required", "detail": "only the owner removes members"})
    decks_svc.remove_member(store(), deck, user, uid)
    return {"removed": uid}


@router.post("/decks/{deck_id}/invitations", status_code=201)
def create_invitation(deck_id: str, body: InvitationCreate, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    if not can_invite(store(), deck, user):
        raise HTTPException(403, {"code": "role_required", "detail": "curators and owners invite"})
    inv = decks_svc.create_invitation(store(), deck, user, body.email, body.role, body.expires_in_days)
    from auth import WEB_URL
    return {**inv, "accept_url": f"{WEB_URL}/invitations/{inv['link_token']}"}


@router.get("/decks/{deck_id}/invitations")
def list_invitations(deck_id: str, user: User = Depends(require_user)):
    deck = deck_or_404(deck_id)
    require_role(store(), deck, user, "curator")
    return [i for i in store().find("invitations", deck_id=deck.id) if not i.get("accepted_at")]


@router.post("/invitations/{token}/accept")
def accept(token: str, user: User = Depends(require_account)):
    return decks_svc.accept_invitation(store(), token, user)

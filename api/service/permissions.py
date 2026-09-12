"""Deck-scoped authorization (spec §2). Pure functions over the store; raise HTTPException(403, role_required)."""
from __future__ import annotations

from fastapi import HTTPException

from auth import is_admin
from models import Card, Deck, User

ROLE_ORDER = {"none": 0, "guest": 0, "reader": 1, "member": 2, "curator": 3, "owner": 4}


def membership(store, deck_id: str, user_id: str | None) -> dict | None:
    if not user_id:
        return None
    rows = store.find("memberships", deck_id=deck_id, user_id=user_id)
    return rows[0] if rows else None


def role_in_deck(store, deck: Deck, user: User | None) -> str:
    """owner | curator | member | reader (signed-in non-member) | guest | none."""
    if user is None:
        return "none"
    if deck.owner_id == user.id:
        return "owner"
    m = membership(store, deck.id, user.id)
    if m:
        return m["role"]
    return "reader"  # guests are temporary accounts: same standing as any signed-in reader


def at_least(role: str, min_role: str) -> bool:
    return ROLE_ORDER.get(role, 0) >= ROLE_ORDER[min_role]


def can_view(store, deck: Deck, user: User | None, share_token: str | None = None) -> bool:
    if deck.visibility == "public":
        return True
    if deck.visibility == "unlisted":
        return True  # "with link": reaching the resource is the link
    if is_admin(user):
        return True
    return at_least(role_in_deck(store, deck, user), "member")


def require_view(store, deck: Deck, user: User | None, share_token: str | None = None) -> None:
    if not can_view(store, deck, user, share_token):
        raise HTTPException(404 if user is None else 403, {"code": "role_required", "detail": "this deck is private"})


def require_role(store, deck: Deck, user: User | None, min_role: str) -> str:
    role = role_in_deck(store, deck, user)
    if not at_least(role, min_role):
        if user is None:
            raise HTTPException(401, {"code": "unauthenticated", "detail": "sign in"})
        raise HTTPException(403, {"code": "role_required", "detail": f"needs {min_role} on this deck", "role": role, "required": min_role})
    return role


def can_create_card(store, deck: Deck, user: User | None) -> bool:
    role = role_in_deck(store, deck, user)
    if at_least(role, "curator"):
        return True
    return role == "member" and deck.settings.who_can_create_cards == "members"


def is_maker(card: Card, user: User | None) -> bool:
    return bool(user) and card.maker_id == user.id


def is_approved_editor(store, card: Card, deck: Deck, user: User | None) -> bool:
    """Makers approve people, never edits. `approved_editors` = "*" resolves against the deck policy."""
    if user is None:
        return False
    role = role_in_deck(store, deck, user)
    if not at_least(role, "member"):
        return False
    ae = card.approved_editors
    if isinstance(ae, list):
        return user.id in ae
    policy = deck.settings.default_editor_policy
    if policy == "any_member":
        return True
    if policy == "curators":
        return at_least(role, "curator")
    return False  # maker_list with no list set: nobody yet


def can_propose_symbol(store, deck: Deck, user: User | None) -> bool:
    return at_least(role_in_deck(store, deck, user), "member")


def can_manage_symbols(store, deck: Deck, user: User | None) -> bool:
    return at_least(role_in_deck(store, deck, user), "curator")


def can_manage_members(store, deck: Deck, user: User | None) -> bool:
    return role_in_deck(store, deck, user) == "owner"


def can_invite(store, deck: Deck, user: User | None) -> bool:
    return at_least(role_in_deck(store, deck, user), "curator")


def can_edit_settings(store, deck: Deck, user: User | None, section: str = "general") -> bool:
    role = role_in_deck(store, deck, user)
    if section in ("style_guide", "structure"):
        return at_least(role, "curator")
    return role == "owner"


def can_host_session(store, deck: Deck, user: User | None) -> bool:
    return at_least(role_in_deck(store, deck, user), "member")


def can_join_session_as_reader(store, deck: Deck, user: User | None, guests_allowed: bool | None = None) -> bool:
    if user is None:
        return False
        return allowed and can_view(store, deck, user)
    return can_view(store, deck, user)


def can_read_card(store, deck: Deck, user: User | None) -> bool:
    """Submit a reading: guests too, if the deck allows guest readers (private decks: members only)."""
    if user is None:
        return False
    return can_view(store, deck, user)


def can_fork(store, deck: Deck, user: User | None) -> bool:
    if user is None:
        return False
    return deck.settings.allow_forks and can_view(store, deck, user) and at_least(role_in_deck(store, deck, user), "reader")

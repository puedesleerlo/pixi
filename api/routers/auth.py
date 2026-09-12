from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

import auth as A
from models import MagicBody, UpgradeBody, User
from routers.deps import store

router = APIRouter(prefix="/api", tags=["auth"])


def _session(response: Response, user: User) -> dict:
    token = A.make_session_token(user.id)
    A.set_session_cookie(response, token)
    return {"token": token, "user": A.public_user(user)}


@router.post("/auth/guest")
def guest(response: Response, body: dict | None = None, user: User | None = Depends(A.current_user)):
    """Continue as guest. Idempotent: an existing session is returned as is."""
    body = body or {}
    if user is not None:
        return _session(response, user)
    u = A.create_guest(name=body.get("name") or body.get("nickname") or "guest", locale=body.get("locale") or "en")
    return _session(response, u)


@router.post("/auth/magic")
def magic(body: MagicBody):
    """Dev magic link: with no mail provider the login URL is returned directly."""
    return A.create_magic_link(body.email, body.name, body.locale)


@router.get("/auth/magic/{token}")
def magic_verify(token: str, response: Response, redirect: int = 0):
    u = A.consume_magic_token(token)
    if redirect:
        r = RedirectResponse(A.WEB_URL + "/", status_code=302)
        A.set_session_cookie(r, A.make_session_token(u.id))
        return r
    return _session(response, u)


@router.post("/auth/upgrade")
def upgrade(body: UpgradeBody, response: Response, user: User = Depends(A.require_user)):
    if not user.is_guest:
        return _session(response, user)
    u = A.upgrade_guest(user, body.email, body.name)
    return _session(response, u)


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(A.COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User | None = Depends(A.current_user)):
    if user is None:
        return {"user": None}
    s = store()
    memberships = s.find("memberships", user_id=user.id)
    decks = []
    for m in memberships:
        d = s.get("decks", m["deck_id"])
        if d:
            decks.append({"deck_id": d["id"], "slug": d["slug"], "name": d["name"], "role": m["role"], "visibility": d.get("visibility"), "stats": d.get("stats")})
    return {"user": A.public_user(user), "decks": decks}


@router.patch("/me")
def patch_me(body: dict, user: User = Depends(A.require_user)):
    for k in ("name", "locale", "avatar_url"):
        if k in body and body[k] is not None:
            setattr(user, k, body[k])
    return {"user": A.public_user(A.save_user(user))}

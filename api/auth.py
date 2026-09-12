"""Identity (spec §2.1, contract §3).

Sessions: token `<user_id>.<exp>.<hmac>` signed with PIXIE_SECRET, carried in cookie `pixie_session`
or `Authorization: Bearer`. Guests are Users without email. Dev magic link returns the login URL
directly when no mail provider is configured. Auth0 RS256 JWTs are accepted when AUTH0_DOMAIN and
AUTH0_AUDIENCE are set.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

from fastapi import Depends, HTTPException, Request, Response

from models import User, now_iso

SECRET = os.environ.get("PIXIE_SECRET") or "dev-secret-change-me"
if SECRET == "dev-secret-change-me":
    print("[auth] PIXIE_SECRET not set — using the dev secret (fine locally, never in production)")
COOKIE = "pixie_session"
SESSION_TTL = 90 * 24 * 3600
MAGIC_TTL = 15 * 60
WEB_URL = (os.environ.get("PIXIE_WEB_URL") or "http://localhost:3000").rstrip("/")
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("PIXIE_ADMIN_EMAILS", "").split(",") if e.strip()}
AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE")

_state: dict[str, Any] = {"store": None}


def bind(store) -> None:
    _state["store"] = store


def store():
    return _state["store"]


def new_id(prefix: str, n: int = 10) -> str:
    return prefix + secrets.token_urlsafe(n)[:n]


# ----------------------------------------------------------------------------- tokens
def _sig(msg: str) -> str:
    return hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]


def make_session_token(user_id: str, ttl: int = SESSION_TTL) -> str:
    exp = int(time.time()) + ttl
    msg = f"{user_id}.{exp}"
    return f"{msg}.{_sig(msg)}"


def parse_session_token(token: str | None) -> str | None:
    if not token or token.count(".") != 2:
        return None
    user_id, exp, sig = token.split(".")
    if not hmac.compare_digest(sig, _sig(f"{user_id}.{exp}")):
        return None
    try:
        if int(exp) < time.time():
            return None
    except ValueError:
        return None
    return user_id


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE, token, max_age=SESSION_TTL, httponly=True, samesite="lax", path="/")


# ----------------------------------------------------------------------------- users
def get_user(user_id: str | None) -> User | None:
    if not user_id:
        return None
    d = store().get("users", user_id)
    return User(**d) if d else None


def user_by_email(email: str) -> User | None:
    rows = store().find("users", email=email.strip().lower())
    return User(**rows[0]) if rows else None


def save_user(u: User) -> User:
    u.updated_at = now_iso()
    store().put("users", u.to_doc())
    return u


def create_guest(name: str = "guest", locale: str = "en") -> User:
    u = User(id=new_id("u_"), name=name or "guest", locale=locale if locale in ("en", "es") else "en", guest_token=secrets.token_urlsafe(16))
    return save_user(u)


def is_admin(u: User | None) -> bool:
    return bool(u and u.email and u.email.lower() in ADMIN_EMAILS)


# ----------------------------------------------------------------------------- magic link (dev)
def create_magic_link(email: str, name: str | None = None, locale: str | None = None) -> dict:
    email = email.strip().lower()
    u = user_by_email(email)
    if u is None:
        u = User(id=new_id("u_"), email=email, name=name or email.split("@")[0], locale=locale or "en")
        save_user(u)
    token = secrets.token_urlsafe(24)
    store().put("magic_tokens", {"id": token, "user_id": u.id, "exp": int(time.time()) + MAGIC_TTL, "used": False, "created_at": now_iso()})
    login_url = f"{WEB_URL}/auth/magic/{token}"
    sent = False  # no mail provider in this build; the URL is returned to the caller (dev banner in the UI)
    return {"login_url": login_url, "token": token, "sent": sent, "user_id": u.id}


def consume_magic_token(token: str) -> User:
    row = store().get("magic_tokens", token)
    if not row or row.get("used") or row.get("exp", 0) < time.time():
        raise HTTPException(400, {"code": "magic_invalid", "detail": "this sign-in link is invalid or expired"})
    row["used"] = True
    store().put("magic_tokens", row)
    u = get_user(row["user_id"])
    if u is None:
        raise HTTPException(404, "user not found")
    return u


# ----------------------------------------------------------------------------- Auth0 (optional)
_jwks_cache: dict[str, Any] = {}


def _auth0_user(token: str) -> User | None:
    if not (AUTH0_DOMAIN and AUTH0_AUDIENCE) or token.count(".") != 2:
        return None
    try:
        import jwt
        from jwt import PyJWKClient

        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            return None
        client = _jwks_cache.get("client") or PyJWKClient(f"https://{AUTH0_DOMAIN}/.well-known/jwks.json")
        _jwks_cache["client"] = client
        key = client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=AUTH0_AUDIENCE, issuer=f"https://{AUTH0_DOMAIN}/")
    except Exception:
        return None
    sub = claims.get("sub")
    rows = store().find("users", auth0_sub=sub)
    if rows:
        return User(**rows[0])
    email = (claims.get("email") or "").lower() or None
    u = user_by_email(email) if email else None
    if u is None:
        u = User(id=new_id("u_"), email=email, name=claims.get("name") or (email or sub), avatar_url=claims.get("picture"))
    u.auth0_sub = sub
    return save_user(u)


# ----------------------------------------------------------------------------- dependencies
def token_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    q = request.query_params.get("token")  # EventSource cannot send headers; SSE clients pass the token in the URL
    if q:
        return q
    return request.cookies.get(COOKIE)


def current_user(request: Request) -> User | None:
    token = token_from_request(request)
    if not token:
        return None
    uid = parse_session_token(token)
    if uid:
        return get_user(uid)
    return _auth0_user(token)


def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(401, {"code": "unauthenticated", "detail": "sign in or continue as guest"})
    return user


def require_account(user: User = Depends(require_user)) -> User:
    """Guests are temporary accounts: everything a member can do, a guest can do (owner's decision, Sat 04:15)."""
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not is_admin(user):
        raise HTTPException(403, {"code": "role_required", "detail": "admin only"})
    return user


def upgrade_guest(guest: User, email: str, name: str | None = None) -> User:
    """Merge a guest into an account: readings, memberships and sessions keep working under the account id."""
    email = email.strip().lower()
    account = user_by_email(email)
    s = store()
    if account is None:
        guest.email = email
        guest.name = name or guest.name
        guest.guest_token = None
        guest.upgraded_from_guest_at = now_iso()
        return save_user(guest)
    for coll, field in (("readings", "reader_id"), ("memberships", "user_id"), ("notifications", "user_id"), ("cards", "maker_id")):
        for d in s.find(coll, **{field: guest.id}):
            d[field] = account.id
            s.put(coll, d)
    for d in s.find("sessions"):
        changed = False
        for p in d.get("players", []):
            if p.get("user_or_guest_id") == guest.id:
                p["user_or_guest_id"] = account.id
                changed = True
        if changed:
            s.put("sessions", d)
    s.delete("users", guest.id)
    account.upgraded_from_guest_at = now_iso()
    return save_user(account)


def public_user(u: User | None) -> dict | None:
    if u is None:
        return None
    return {"id": u.id, "name": u.name, "email": u.email, "avatar_url": u.avatar_url, "locale": u.locale,
            "is_guest": u.is_guest, "is_admin": is_admin(u), "created_at": u.created_at}

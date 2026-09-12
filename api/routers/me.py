"""Routes the web app relies on beyond spec §11: /me/decks, /me/inbox, /me/activity, structure-template
aliases, style preview (local provider), deck session list, Auth0 login redirect."""
from __future__ import annotations

import base64
import os
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from auth import current_user, require_user
from models import Deck, User
from routers.deps import deck_or_404, store, storage, viewable_deck
from service import decks as decks_svc, measure
from service.permissions import is_approved_editor, role_in_deck

router = APIRouter(prefix="/api", tags=["me"])


class PreviewBody(BaseModel):
    style_guide: dict | None = None
    style_from_base_deck_id: str | None = None
    symbol_keys: list[str] | None = None


@router.get("/me/decks")
def my_decks(user: User = Depends(require_user)):
    out = []
    for m in store().find("memberships", user_id=user.id):
        d = store().get("decks", m["deck_id"])
        if d:
            out.append({"deck_id": d["id"], "slug": d.get("slug"), "name": d.get("name"), "role": m.get("role"), "visibility": d.get("visibility"),
                        "stats": d.get("stats") or {}, "origin": d.get("origin")})
    return out


@router.get("/me/inbox")
def my_inbox(user: User = Depends(require_user)):
    """Cards waiting for you: to read (decks you belong to), open for your edit, requests to your cards."""
    to_read, open_for_edit, requests = [], [], []
    for m in store().find("memberships", user_id=user.id):
        deck = store().get("decks", m["deck_id"])
        if not deck:
            continue
        try:
            dm = decks_svc.get_deck(store(), deck["id"])
        except Exception:
            continue
        for c in store().find("cards", deck_id=deck["id"]):
            if c.get("status") == "reading" and c.get("maker_id") != user.id and c.get("current_version_id"):
                if not any(r.get("reader_id") == user.id for r in store().find("readings", version_id=c["current_version_id"])):
                    to_read.append({"card_id": c["id"], "deck_id": deck["id"], "deck_slug": deck.get("slug"), "position_key": c.get("position_key"), "title": c.get("title")})
            if c.get("status") == "open":
                try:
                    from models import Card

                    if is_approved_editor(store(), Card(**c), dm, user):
                        open_for_edit.append({"card_id": c["id"], "deck_id": deck["id"], "deck_slug": deck.get("slug"), "position_key": c.get("position_key"), "title": c.get("title")})
                except Exception:
                    pass
            if c.get("maker_id") == user.id:
                for rq in c.get("edit_requests") or []:
                    if rq.get("status") == "open":
                        requests.append({"card_id": c["id"], "deck_id": deck["id"], "deck_slug": deck.get("slug"), "position_key": c.get("position_key"), "request": rq})
    return {"to_read": to_read[:50], "open_for_edit": open_for_edit[:50], "requests": requests[:50]}


@router.get("/me/activity")
def my_activity(limit: int = 50, user: User = Depends(require_user)):
    deck_ids = {m["deck_id"] for m in store().find("memberships", user_id=user.id)}
    acts = [a for a in store().all("activities") if a.get("deck_id") in deck_ids]
    acts.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    return acts[:limit]


@router.get("/structure-templates")
def structure_templates():
    return [t.model_dump() for t in decks_svc.structures().values()]


@router.get("/structure-templates/{key}")
def structure_template(key: str):
    try:
        return decks_svc.structure(key).model_dump()
    except Exception:
        raise HTTPException(404, {"code": "not_found", "detail": "no such structure template"})


@router.get("/decks/{deck_id}/sessions")
def deck_sessions(deck: Deck = Depends(viewable_deck)):
    rows = store().find("sessions", deck_id=deck.id)
    rows.sort(key=lambda s: s.get("created_at") or "", reverse=True)
    return [{"id": s["id"], "code": s["code"], "mode": s["mode"], "state": s["state"], "host_id": s["host_id"], "n_players": len(s.get("players", [])),
             "created_at": s.get("created_at"), "updated_at": s.get("updated_at")} for s in rows[:50]]


@router.post("/decks/preview-style")
def preview_style(body: PreviewBody, user: User = Depends(require_user)):
    """A quota-free test card rendered by the local collage provider from the style guide (spec §5.2 step 4)."""
    try:
        from pixie.imaging.providers.local import LocalCollageProvider
        from pixie.imaging.prompts import assemble_generate
    except Exception as e:
        raise HTTPException(503, {"code": "provider_unavailable", "detail": str(e)})
    sg = body.style_guide or {}
    if body.style_from_base_deck_id and not sg:
        base = decks_svc.base_deck(store(), body.style_from_base_deck_id)
        if base:
            sg = decks_svc.style_from_base(store(), base).model_dump()
    reg = None
    if body.style_from_base_deck_id:
        base = decks_svc.base_deck(store(), body.style_from_base_deck_id)
        reg = store().get("base_symbol_registries", (base or {}).get("symbol_registry_id") or "") if base else None
    if reg is None:  # "Describe it" / uploads: borrow three Smith exemplars so the style is visible on something
        reg = store().get("base_symbol_registries", "reg_smith1909")
    preferred = ["star", "nude_figure", "water_falling", "crown", "sun", "moon"]
    exemplars = []
    syms_all = (reg or {}).get("symbols") or []
    order = sorted(syms_all, key=lambda x: (preferred.index(x.get("key")) if x.get("key") in preferred else 99))
    for s in order[:40]:
        if body.symbol_keys and s.get("key") not in body.symbol_keys:
            continue
        url = (s.get("exemplar") or {}).get("image_url")
        if url and url.startswith("/static/"):
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), url.lstrip("/"))
            if os.path.exists(path):
                exemplars.append({"symbol_id": s.get("key"), "name": s.get("name"), "gloss": s.get("gloss"), "placement": s.get("placement", "any"), "path": path})
        if len(exemplars) >= 3:
            break
    symbols = [{"name": e["name"], "gloss": e["gloss"], "placement": e.get("placement")} for e in exemplars]
    prompt = assemble_generate(sg, "Preview", symbols, "a single scene that shows these symbols together")
    res, note = None, None
    try:  # the configured provider (Gemini when keyed); the preview is outside any deck quota
        from pixie.imaging.providers.base import get_provider

        prov = get_provider()
        if getattr(prov, "name", "local") != "local":
            res = prov.generate(prompt, [], sg.get("aspect", "2.75x4.75"), 1, seed=None, negative_prompt=sg.get("negative_prompt"))
    except Exception as e:
        note = f"{type(e).__name__}: {str(e)[:120]}"
    if res is None:  # local collage of the exemplars — always available
        res = LocalCollageProvider().generate(prompt, [], sg.get("aspect", "2.75x4.75"), 1, seed=7, style_guide=sg, symbol_exemplars=exemplars)
    img = res.images[0]
    key = storage().put(f"previews/{user.id}/style-{int(time.time())}.png", img, "image/png")
    return {"image_url": storage().url(key), "provider": res.provider, "model": getattr(res, "model", None), "prompt_full": prompt, "fallback_note": note}


@router.get("/auth/auth0/login")
def auth0_login():
    domain, client_id = os.environ.get("AUTH0_DOMAIN"), os.environ.get("AUTH0_CLIENT_ID")
    if not domain or not client_id:
        raise HTTPException(404, {"code": "not_configured", "detail": "Auth0 is not configured (AUTH0_DOMAIN, AUTH0_CLIENT_ID); use the magic link"})
    web = os.environ.get("PIXIE_WEB_URL", "http://localhost:3000").rstrip("/")
    return RedirectResponse(f"https://{domain}/authorize?response_type=token&client_id={client_id}&redirect_uri={web}/auth/callback&scope=openid%20profile%20email&audience={os.environ.get('AUTH0_AUDIENCE', '')}")

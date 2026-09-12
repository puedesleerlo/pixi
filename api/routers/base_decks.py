"""Base-deck catalog routes (spec v5 §11 'Base decks' + admin ingest). Stream B2.

Store access: `from main import state` lazily inside handlers (B1's main.py sets `state["store"]`);
`set_store_getter(fn)` overrides it (used by the slice-2 tests and by any app that mounts this router alone).
"""
from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from service import base_decks as svc

router = APIRouter(prefix="/api", tags=["base-decks"])
_store_getter: Callable[[], object] | None = None


def set_store_getter(fn: Callable[[], object]) -> None:
    global _store_getter
    _store_getter = fn


def store():
    if _store_getter is not None:
        return _store_getter()
    from main import state  # lazy: B1 owns main.py

    return state["store"]


def _storage():
    try:
        from main import state

        return state.get("storage")
    except Exception:
        return None


def _admin_guard():
    """Admin-only when `auth.require_admin` exists; open in dev otherwise (documented in README-api)."""
    try:
        from auth import require_admin  # type: ignore

        return require_admin
    except Exception:
        return lambda: None


def _public_deck(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in ("rights_checklist",)} | {"rights_checklist_complete": _checklist_complete(d)}


def _checklist_complete(d: dict) -> bool:
    c = d.get("rights_checklist") or {}
    return all(c.get(k) for k in ("source_page", "license_text", "date", "reviewer"))


@router.get("/base-decks")
def list_decks():
    return [_public_deck(d) for d in svc.list_base_decks(store())]


@router.get("/base-decks/{slug}")
def get_deck(slug: str):
    d = svc.get_base_deck(store(), slug)
    if d is None:
        raise HTTPException(404, "no such base deck")
    out = dict(d)
    out["rights_checklist_complete"] = _checklist_complete(d)
    out["n_symbols"] = len(svc.base_symbols(store(), slug))
    return out


@router.get("/base-decks/{slug}/cards")
def get_cards(slug: str):
    if svc.get_base_deck(store(), slug) is None:
        raise HTTPException(404, "no such base deck")
    return svc.base_cards(store(), slug)


@router.get("/base-decks/{slug}/symbols")
def get_symbols(slug: str, position_key: str | None = None):
    if svc.get_base_deck(store(), slug) is None:
        raise HTTPException(404, "no such base deck")
    if position_key:
        return svc.symbols_for_position(store(), slug, position_key)
    reg = svc.registry(store(), slug)
    return {"slug": slug, "version": (reg or {}).get("version"), "symbols": (reg or {}).get("symbols", []),
            "symbols_by_card": (reg or {}).get("symbols_by_card", {})}


class IngestBody(BaseModel):
    slug: str
    download: bool = False


@router.post("/admin/base-decks/ingest")
def admin_ingest(body: IngestBody, _: object = Depends(_admin_guard())):
    try:
        return svc.ingest(store(), _storage() if body.download else None, body.slug, download=body.download)
    except KeyError as e:
        raise HTTPException(404, str(e))

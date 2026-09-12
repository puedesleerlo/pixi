"""Symbols — the deck-level vocabulary (spec §3.6, §5.3)."""
from __future__ import annotations

import base64
import io
import json
import os
import re

import httpx
from fastapi import HTTPException

from auth import new_id
from models import (Deck, Symbol, SymbolDraft, SymbolMeasured, SymbolPatch, SymbolProposal, User, now_iso)
from service import activity, notifications

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("PIXIE_DATA_DIR", os.path.join(HERE, "..", "data"))
UA = {"User-Agent": "pixie/0.5 (datos@corlide.org)"}


def slug_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40] or "symbol"


def unique_key(store, deck_id: str, base: str, exclude_id: str | None = None) -> str:
    key, k = base, 2
    while any(s["id"] != exclude_id for s in store.find("symbols", deck_id=deck_id, key=key)):
        key = f"{base}_{k}"
        k += 1
    return key


def get_symbol(store, sid: str) -> Symbol:
    d = store.get("symbols", sid)
    if d is None:
        raise HTTPException(404, {"code": "not_found", "detail": "no such symbol"})
    return Symbol(**d)


def save_symbol(store, s: Symbol) -> Symbol:
    s.updated_at = now_iso()
    store.put("symbols", s.to_doc())
    return s


def list_symbols(store, deck_id: str, status: str | None = None) -> list[Symbol]:
    rows = store.find("symbols", deck_id=deck_id, status=status) if status else store.find("symbols", deck_id=deck_id)
    rows.sort(key=lambda s: (s.get("origin") != "inherited_base", s.get("name") or ""))
    return [Symbol(**r) for r in rows]


# ----------------------------------------------------------------------------- exemplars
def _fetch_image(storage, url: str) -> bytes:
    if url.startswith("/media/"):
        data = storage.get(url[len("/media/"):].split("?")[0])
        if data is None:
            raise HTTPException(404, {"code": "not_found", "detail": "image not in storage"})
        return data
    if url.startswith("http"):
        r = httpx.get(url, headers=UA, timeout=30, follow_redirects=True)
        r.raise_for_status()
        return r.content
    p = os.path.join(HERE, url.lstrip("/"))
    if os.path.exists(p):
        with open(p, "rb") as f:
            return f.read()
    raise HTTPException(422, {"code": "validation", "detail": f"cannot read image {url}"})


def crop_exemplar(storage, image_bytes: bytes, bbox: list[float] | None, key: str) -> str:
    from PIL import Image

    im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if bbox and len(bbox) == 4:
        x0, y0, x1, y1 = bbox
        w, h = im.size
        box = (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
        if box[2] - box[0] < 4 or box[3] - box[1] < 4:
            raise HTTPException(422, {"code": "validation", "detail": "bbox too small"})
        im = im.crop(box)
    im.thumbnail((512, 512))
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return storage.put(key, out.getvalue(), "image/png")


def resolve_exemplar(store, storage, deck: Deck, draft: SymbolDraft | SymbolPatch, sid: str) -> dict | None:
    """Returns an Exemplar dict or None if the draft carries no exemplar."""
    if getattr(draft, "exemplar_upload", None):
        raw = draft.exemplar_upload
        if "," in raw and raw.strip().startswith("data:"):
            raw = raw.split(",", 1)[1]
        try:
            data = base64.b64decode(raw)
        except Exception:
            raise HTTPException(422, {"code": "validation", "detail": "exemplar_upload must be base64"})
        key = crop_exemplar(storage, data, None, f"decks/{deck.id}/symbols/{sid}.png")
        return {"image_url": storage.url(key), "origin": "upload", "source_ref": None}
    src = getattr(draft, "exemplar_from_base_card", None)
    if src and src.get("base_card_id"):
        bc = store.get("base_cards", src["base_card_id"])
        if bc is None:
            raise HTTPException(404, {"code": "not_found", "detail": "no such base card"})
        data = _fetch_image(storage, bc["image_url"])
        key = crop_exemplar(storage, data, src.get("bbox"), f"decks/{deck.id}/symbols/{sid}.png")
        return {"image_url": storage.url(key), "origin": "base_crop", "source_ref": bc["id"]}
    if getattr(draft, "exemplar_image_url", None):
        return {"image_url": draft.exemplar_image_url, "origin": "upload", "source_ref": None}
    return None


# ----------------------------------------------------------------------------- create / import
def create_symbol(store, storage, deck: Deck, user: User, draft: SymbolDraft, origin: str = "community",
                  proposed_by: str | None = None, approved_by: str | None = None) -> Symbol:
    sid = new_id("sy_")
    key = unique_key(store, deck.id, draft.key or slug_key(draft.name))
    if len(draft.declared_axes) != 8 or any(abs(a) > 3 for a in draft.declared_axes):
        raise HTTPException(422, {"code": "validation", "detail": "declared_axes must be 8 values in -3..3"})
    exemplar = resolve_exemplar(store, storage, deck, draft, sid) or {"image_url": None, "origin": "upload", "source_ref": None}
    s = Symbol(id=sid, deck_id=deck.id, key=key, name=draft.name.strip(), gloss=draft.gloss.strip(), tags=draft.tags,
               declared_axes=draft.declared_axes, declared_text=draft.declared_text, exemplar=exemplar, placement=draft.placement,
               origin=origin, attestations=draft.attestations, status="active", proposed_by=proposed_by,
               approved_by=approved_by or user.id, approved_at=now_iso())
    save_symbol(store, s)
    activity.log(store, deck.id, user.id, "symbol.added", {"symbol_id": sid, "key": key, "origin": origin})
    return s


def base_registry(store, base_slug: str) -> tuple[dict | None, list[dict]]:
    base = None
    rows = store.find("base_decks", slug=base_slug)
    if rows:
        base = rows[0]
        syms = store.find("base_symbols", base_deck_id=base["id"])
        if syms:
            return base, syms
    path = os.path.join(DATA_DIR, "base_decks", base_slug, "registry.json")
    if os.path.exists(path):
        with open(path) as f:
            raw = json.load(f)
        items = raw if isinstance(raw, list) else raw.get("symbols", [])
        return base, [{"id": x.get("id") or f"bs_{base_slug}_{x['key']}", "base_deck_slug": base_slug, **x} for x in items]
    return base, []


def import_from_base(store, storage, deck: Deck, base_slug: str, keys: list[str] | None, user: User) -> list[Symbol]:
    base, registry = base_registry(store, base_slug)
    if not registry:
        return []
    wanted = set(keys) if keys is not None else None
    have = {s["key"] for s in store.find("symbols", deck_id=deck.id)}
    out = []
    for bs in registry:
        if wanted is not None and bs["key"] not in wanted:
            continue
        if bs["key"] in have:
            continue
        axes = bs.get("attested_axes") or bs.get("declared_axes") or [0.0] * 8
        ex = bs.get("exemplar") or {}
        s = Symbol(id=new_id("sy_"), deck_id=deck.id, key=bs["key"], name=bs.get("name", bs["key"]), gloss=bs.get("gloss", ""),
                   tags=bs.get("tags", []), declared_axes=axes, declared_text=bs.get("attested_text") or bs.get("declared_text") or "",
                   exemplar={"image_url": ex.get("image_url"), "origin": "base_crop", "source_ref": ex.get("source_card")},
                   placement=bs.get("placement", "any") or "any", origin="inherited_base",
                   inherited_from={"base_deck_id": (base or {}).get("id"), "symbol_id": bs.get("id") or bs["key"]},
                   attestations=bs.get("attestations", []), prior_axes=bs.get("attested_axes"), prior_source="attestation" if bs.get("attested_axes") else None,
                   status="active", approved_by=user.id, approved_at=now_iso())
        save_symbol(store, s)
        out.append(s)
    if out:
        activity.log(store, deck.id, user.id, "symbols.imported", {"base_deck": base_slug, "n": len(out)})
    return out


# ----------------------------------------------------------------------------- patch / merge / retire
def patch_symbol(store, storage, deck: Deck, s: Symbol, body: SymbolPatch, user: User) -> Symbol:
    data = body.model_dump(exclude_none=True)
    ex = resolve_exemplar(store, storage, deck, body, s.id)
    for k in ("exemplar_upload", "exemplar_from_base_card"):
        data.pop(k, None)
    if data.get("declared_axes") is not None and (len(data["declared_axes"]) != 8 or any(abs(a) > 3 for a in data["declared_axes"])):
        raise HTTPException(422, {"code": "validation", "detail": "declared_axes must be 8 values in -3..3"})
    updated = Symbol(**{**s.model_dump(), **data})  # rename keeps `key`
    if ex:
        updated.exemplar = ex
    activity.log(store, deck.id, user.id, "symbol.updated", {"symbol_id": s.id, "fields": sorted(data)})
    return save_symbol(store, updated)


def merge_symbol(store, deck: Deck, s: Symbol, into: Symbol, user: User) -> dict:
    if s.id == into.id or into.deck_id != deck.id or s.deck_id != deck.id:
        raise HTTPException(422, {"code": "validation", "detail": "merge needs two different symbols of this deck"})
    if into.status != "active":
        raise HTTPException(422, {"code": "validation", "detail": "the target symbol must be active"})
    n_versions = 0
    for v in store.find("versions", deck_id=deck.id):
        changed = False
        for field in ("symbols_declared", "symbols_detected"):
            items = v.get(field) or []
            if any(x.get("symbol_id") == s.id for x in items):
                seen, out = set(), []
                for x in items:
                    x = {**x, "symbol_id": into.id} if x.get("symbol_id") == s.id else x
                    if x["symbol_id"] in seen:
                        continue
                    seen.add(x["symbol_id"])
                    out.append(x)
                v[field] = out
                changed = True
        if changed:
            v["updated_at"] = now_iso()
            store.put("versions", v)
            n_versions += 1
    s.status = "merged"
    s.merged_into_symbol_id = into.id
    save_symbol(store, s)
    into.attestations = into.attestations + [a for a in s.attestations if a not in into.attestations]
    into.tags = sorted(set(into.tags) | set(s.tags))
    save_symbol(store, into)
    activity.log(store, deck.id, user.id, "symbol.merged", {"symbol_id": s.id, "into": into.id, "versions_rewritten": n_versions})
    return {"merged": s.id, "into": into.id, "versions_rewritten": n_versions}


def retire_symbol(store, deck: Deck, s: Symbol, user: User) -> Symbol:
    s.status = "retired"
    activity.log(store, deck.id, user.id, "symbol.retired", {"symbol_id": s.id})
    return save_symbol(store, s)


# ----------------------------------------------------------------------------- proposals (curated, never voted)
def propose(store, deck: Deck, user: User, draft: SymbolDraft, note: str) -> SymbolProposal:
    p = SymbolProposal(id=new_id("sp_"), deck_id=deck.id, symbol_draft=draft, note=note, proposed_by=user.id)
    store.put("symbol_proposals", p.to_doc())
    activity.log(store, deck.id, user.id, "symbol.proposed", {"proposal_id": p.id, "name": draft.name})
    for m in store.find("memberships", deck_id=deck.id):
        if m["role"] in ("owner", "curator") and m["user_id"] != user.id:
            notifications.notify(store, m["user_id"], "proposal.received", f"{user.name} proposed the symbol “{draft.name}” in {deck.name}", deck_id=deck.id)
    return p


def decide_proposal(store, storage, deck: Deck, pid: str, user: User, action: str, note: str | None) -> SymbolProposal:
    d = store.get("symbol_proposals", pid)
    if d is None or d.get("deck_id") != deck.id:
        raise HTTPException(404, {"code": "not_found", "detail": "no such proposal"})
    p = SymbolProposal(**d)
    if p.status != "open":
        raise HTTPException(409, {"code": "already_decided", "detail": f"proposal is {p.status}"})
    p.decided_by, p.decision_note = user.id, note
    if action == "approve":
        s = create_symbol(store, storage, deck, user, p.symbol_draft, origin="community", proposed_by=p.proposed_by, approved_by=user.id)
        p.status, p.symbol_id = "approved", s.id
        notifications.notify(store, p.proposed_by, "proposal.decided", f"Your symbol “{s.name}” was approved in {deck.name}", deck_id=deck.id)
    else:
        p.status = "declined"
        notifications.notify(store, p.proposed_by, "proposal.decided", f"Your symbol proposal “{p.symbol_draft.name}” was declined in {deck.name}" + (f": {note}" if note else ""), deck_id=deck.id)
    p.updated_at = now_iso()
    store.put("symbol_proposals", p.to_doc())
    activity.log(store, deck.id, user.id, f"symbol.proposal_{p.status}", {"proposal_id": p.id, "symbol_id": p.symbol_id})
    return p


def list_proposals(store, deck_id: str, status: str | None = None) -> list[dict]:
    rows = store.find("symbol_proposals", deck_id=deck_id, status=status) if status else store.find("symbol_proposals", deck_id=deck_id)
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows


# ----------------------------------------------------------------------------- measured block (filled by the grammar job)
def set_measured(store, deck_id: str, measured_by_id: dict[str, dict]) -> int:
    n = 0
    for s in store.find("symbols", deck_id=deck_id):
        m = measured_by_id.get(s["id"])
        if m is None:
            continue
        s["measured"] = SymbolMeasured(**{**s.get("measured", {}), **m}).model_dump()
        s["updated_at"] = now_iso()
        store.put("symbols", s)
        n += 1
    return n


def cards_using(store, deck_id: str, symbol_id: str) -> list[dict]:
    out = []
    for c in store.find("cards", deck_id=deck_id):
        if not c.get("current_version_id"):
            continue
        v = store.get("versions", c["current_version_id"])
        if v and any(x.get("symbol_id") == symbol_id for x in (v.get("symbols_detected") or v.get("symbols_declared") or [])):
            out.append({"card_id": c["id"], "position_key": c.get("position_key"), "title": c.get("title"), "status": c.get("status"),
                        "thumb_url": v.get("thumb_url") or v.get("image_url"), "version_id": v["id"]})
    return out

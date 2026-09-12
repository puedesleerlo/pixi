"""Base-deck catalog (spec v5 §3.2, §9): manifests → base_decks / base_cards / base_symbol_registries.

Plain dicts over the v4 `pixie.store` API (get/put/put_many/find/all/count/delete), so this module has no
dependency on `api/models.py`. Field names follow spec §3.2 and §3.6.

Store docs produced:
  base_decks               {id: "bd_<slug>", slug, name, tradition, year, origin, rights_note, source_urls[],
                            structure_template_id, card_count, status, symbol_registry_id: "reg_<slug>",
                            attestation_sources[], rights_checklist{}, missing[], registry_version, created_at, updated_at}
  base_cards               {id: "bc_<slug>_<position_key>", base_deck_id, slug, position_key, title, image_url, thumb_url,
                            caption, commons_title, license, storage_key?, thumb_key?, attested_meaning_text?, attested_axes?,
                            created_at, updated_at}
  base_symbol_registries   {id: "reg_<slug>", base_deck_id, slug, version, symbols: [Symbol draft], symbols_by_card: {position_key: [{key, salience}]}}
"""
from __future__ import annotations

import io
import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "data"))
UA = {"User-Agent": "pixie-hackcmu/0.1 (datos@corlide.org)"}
THUMB_PX = 600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _read(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


# ----------------------------------------------------------------------------- files
def load_manifests(data_dir: str = DEFAULT_DATA_DIR) -> dict[str, dict]:
    base = os.path.join(data_dir, "base_decks")
    out: dict[str, dict] = {}
    if not os.path.isdir(base):
        return out
    for slug in sorted(os.listdir(base)):
        p = os.path.join(base, slug, "manifest.json")
        if os.path.isfile(p):
            m = _read(p)
            m.setdefault("slug", slug)
            out[m["slug"]] = m
    return out


def load_registry(slug: str, data_dir: str = DEFAULT_DATA_DIR) -> dict | None:
    p = os.path.join(data_dir, "base_decks", slug, "registry.json")
    return _read(p) if os.path.isfile(p) else None


def load_structures(data_dir: str = DEFAULT_DATA_DIR) -> list[dict]:
    p = os.path.join(data_dir, "structures.json")
    return _read(p) if os.path.isfile(p) else []


# ----------------------------------------------------------------------------- images
def _fetch(url: str, cache_dir: str) -> bytes:
    os.makedirs(cache_dir, exist_ok=True)
    name = url.rsplit("/", 1)[-1][:150]
    path = os.path.join(cache_dir, name)
    if os.path.isfile(path):
        with open(path, "rb") as f:
            return f.read()
    # Commons rate-limits bursts (HTTP 429): throttle every download and back off on 429.
    import time
    import urllib.error

    delay = 0.6
    for attempt in range(4):
        time.sleep(delay)
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                retry_after = e.headers.get("Retry-After") if e.headers else None
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 5.0 * (attempt + 1)
                continue
            raise
    with open(path, "wb") as f:
        f.write(data)
    return data


def _normalize(data: bytes, max_side: int = 2048) -> tuple[bytes, bytes, int, int]:
    """→ (jpeg original ≤ max_side, webp thumb ≤ THUMB_PX, width, height)."""
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((max_side, max_side))
    w, h = im.size
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    th = im.copy()
    th.thumbnail((THUMB_PX, THUMB_PX))
    tb = io.BytesIO()
    th.save(tb, "WEBP", quality=85)
    return buf.getvalue(), tb.getvalue(), w, h


# ----------------------------------------------------------------------------- ingestion
def ingest(store, storage=None, slug: str = "smith1909", data_dir: str = DEFAULT_DATA_DIR, job_ctx=None,
           download: bool | None = None) -> dict:
    """Create/refresh the base deck, its cards and its registry in the store.
    With `storage` (anything with put(key, bytes, content_type) -> key and url(key)), images are downloaded,
    normalised and stored; otherwise the Commons URLs are kept. `job_ctx.progress(p, note)` is optional."""
    manifests = load_manifests(data_dir)
    if slug not in manifests:
        raise KeyError(f"no manifest for base deck '{slug}'")
    m = manifests[slug]
    if download is None:
        download = storage is not None
    now = _now()
    deck_id = f"bd_{slug}"
    registry = load_registry(slug, data_dir)
    existing = store.get("base_decks", deck_id) or {}
    deck = {
        "id": deck_id, "slug": slug, "name": m["name"], "tradition": m.get("tradition"), "year": m.get("year"), "origin": m.get("origin"),
        "rights_note": m.get("rights_note"), "source_urls": m.get("source_urls", []), "structure_template_id": m.get("structure_template", "free"),
        "card_count": len(m.get("cards", [])), "status": m.get("status", "planned"), "symbol_registry_id": f"reg_{slug}" if registry else None,
        "attestation_sources": m.get("attestation_sources", []), "rights_checklist": m.get("rights_checklist", {}), "missing": m.get("missing", []),
        "registry_version": (registry or {}).get("version"), "created_at": existing.get("created_at", now), "updated_at": now,
    }
    store.put("base_decks", deck)
    cards = m.get("cards", [])
    n = max(1, len(cards))
    docs = []
    cache_dir = os.path.join(data_dir, "_cache", "images", slug)
    for i, c in enumerate(cards):
        doc = {
            "id": f"bc_{slug}_{c['position_key']}", "base_deck_id": deck_id, "slug": slug, "position_key": c["position_key"], "title": c["title"],
            "image_url": c["image_url"], "thumb_url": c.get("thumb_url") or c["image_url"], "caption": c.get("caption", ""),
            "commons_title": c.get("commons_title"), "license": c.get("license"), "attested_meaning_text": c.get("attested_meaning_text"),
            "attested_axes": c.get("attested_axes"), "created_at": now, "updated_at": now,
        }
        if download and storage is not None:
            try:
                raw = _fetch(c["image_url"], cache_dir)
                jpg, webp, w, h = _normalize(raw)
                key = storage.put(f"base/{slug}/{c['position_key']}.jpg", jpg, "image/jpeg")
                tkey = storage.put(f"base/{slug}/{c['position_key']}.webp", webp, "image/webp")
                doc.update({"storage_key": key, "thumb_key": tkey, "image_url": storage.url(key), "thumb_url": storage.url(tkey), "width": w, "height": h})
            except Exception as e:  # keep the Commons URL; never fail the whole ingest for one image
                doc["download_error"] = f"{type(e).__name__}: {e}"
        docs.append(doc)
        if job_ctx is not None and hasattr(job_ctx, "progress"):
            job_ctx.progress((i + 1) / n, f"{slug}: {c['position_key']}")
    if docs:
        store.put_many("base_cards", docs)
    if registry:
        store.put("base_symbol_registries", {"id": f"reg_{slug}", "base_deck_id": deck_id, "slug": slug, "version": registry.get("version", 1),
                                              "symbols": registry.get("symbols", []), "symbols_by_card": registry.get("symbols_by_card", {}),
                                              "created_at": now, "updated_at": now})
    return {"slug": slug, "cards": len(docs), "symbols": len((registry or {}).get("symbols", [])), "status": deck["status"],
            "downloaded": bool(download and storage is not None)}


def ensure_ingested(store, data_dir: str = DEFAULT_DATA_DIR, slugs: list[str] | None = None) -> list[str]:
    """At boot: ingest (without downloads) every manifest that is not in the store yet."""
    done = []
    for slug in (slugs or list(load_manifests(data_dir))):
        if store.get("base_decks", f"bd_{slug}") is None:
            ingest(store, None, slug, data_dir)
            done.append(slug)
    return done


# ----------------------------------------------------------------------------- reads
def list_base_decks(store) -> list[dict]:
    order = {"ready": 0, "partial": 1, "planned": 2}
    return sorted(store.all("base_decks"), key=lambda d: (order.get(d.get("status"), 9), d.get("year") or 0, d["slug"]))


def get_base_deck(store, slug: str) -> dict | None:
    return store.get("base_decks", f"bd_{slug}")


def base_cards(store, slug: str) -> list[dict]:
    cards = store.find("base_cards", base_deck_id=f"bd_{slug}")
    order = {c["position_key"]: i for i, c in enumerate(load_manifests().get(slug, {}).get("cards", []))}
    return sorted(cards, key=lambda c: order.get(c["position_key"], 10_000))


def registry(store, slug: str) -> dict | None:
    return store.get("base_symbol_registries", f"reg_{slug}")


def base_symbols(store, slug: str) -> list[dict]:
    reg = registry(store, slug)
    return list(reg["symbols"]) if reg else []


def symbols_for_position(store, slug: str, position_key: str) -> list[dict]:
    """[{key, salience}] the base registry says are visible on that base card (used by 'Inherit')."""
    reg = registry(store, slug)
    return list((reg or {}).get("symbols_by_card", {}).get(position_key, []))


def on_startup(state: dict) -> None:
    """main.py startup hook: load every manifest's cards and registry into the store (no downloads)."""
    ensure_ingested(state["store"])

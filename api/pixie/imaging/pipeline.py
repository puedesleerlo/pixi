"""Job handlers: run_generate, run_edit, run_symbol, run_tag. Plain dicts in, plain dicts out.

`ctx` is any object (or dict) providing
    storage_put(key: str, data: bytes, content_type: str) -> str      # returns the stored key
    progress(fraction: float, note: str = "") -> None                 # optional
so the API's job runner can register these without importing anything else.

Payload shapes (all optional keys may be omitted):

run_generate(payload):
  provider: "local"|"gemini"|"flux"|"openai"|None          # None → by environment
  style_guide: {prompt_prefix, negative_prompt, palette[], line, border{style,color}, aspect, style_centroid_embedding?}
  position_title: str|None
  symbols: [{symbol_id, name, gloss, placement?, region?, exemplar_bytes?|exemplar_path?}]   # declared symbols
  prompt_user: str, aspect: "2.75x4.75", n: 1..4, seed: int|None
  style_refs: [bytes|path]                                 # up to 3 reference images (style guide + on-style cards)
  style_centroid: [float]|None                             # precomputed; else computed from style_refs
  registry: [{symbol_id, name, gloss}]                     # the deck's active symbols (for detection)
  storage_prefix: "decks/<deck>/cards/<card>/gen_<job>"

run_edit(payload):
  provider, base_image: bytes|path, op: add|remove|replace|emphasize|deemphasize|reposition|cosmetic
  symbol: {symbol_id, name, gloss, placement?, exemplar_bytes?|exemplar_path?}, to_symbol: same (replace)
  region: {x,y,w,h}|None, placement: str|None, target_region (reposition), how_text: str
  n, seed, fidelity_threshold: 0.85, style_guide, style_refs, style_centroid, registry
  declared: [{symbol_id, placement?, region?}]             # declared symbols on the base version
  storage_prefix
"""
from __future__ import annotations

import io
import time
from typing import Any, Callable, Optional

from PIL import Image

from .detect import detect_symbols, reconcile
from .fidelity import diff_heatmap, fidelity as fidelity_of, image_embed_backend
from .prompts import assemble_edit, assemble_generate, strip_denylist, validate_how_text
from .providers.base import ProviderBlocked, ProviderUnavailable, get_provider, load_image, mask_from_region, png_bytes, zone
from .style import style_centroid, style_score

EXPERIMENT_OPS = {"add", "remove", "replace", "emphasize", "deemphasize", "reposition"}


class _Ctx:
    """Normalises the ctx argument (object with methods, or dict of callables)."""

    def __init__(self, ctx: Any):
        self._put: Callable = getattr(ctx, "storage_put", None) or (ctx.get("storage_put") if isinstance(ctx, dict) else None)
        self._progress: Optional[Callable] = getattr(ctx, "progress", None) or (ctx.get("progress") if isinstance(ctx, dict) else None)
        if self._put is None:
            raise ValueError("ctx needs storage_put(key, data, content_type)")

    def put(self, key: str, data: bytes, content_type: str = "image/png") -> str:
        return self._put(key, data, content_type)

    def progress(self, f: float, note: str = "") -> None:
        if self._progress:
            try:
                self._progress(float(f), note)
            except Exception:
                pass


def _bytes(x: Any) -> Optional[bytes]:
    if x is None:
        return None
    if isinstance(x, (bytes, bytearray)):
        return bytes(x)
    return png_bytes(load_image(x))


def _exemplar_of(sym: Optional[dict]) -> dict:
    sym = sym or {}
    ex: dict[str, Any] = {"symbol_id": sym.get("symbol_id"), "name": sym.get("name")}
    if sym.get("exemplar_bytes") is not None:
        ex["image_bytes"] = sym["exemplar_bytes"]
    elif sym.get("exemplar_path"):
        ex["path"] = sym["exemplar_path"]
    return ex


def _thumb(png: bytes, width: int = 400) -> bytes:
    im = load_image(png)
    im.thumbnail((width, width * 4))
    buf = io.BytesIO()
    im.save(buf, format="WEBP", quality=82)
    return buf.getvalue()


def _centroid(payload: dict):
    c = payload.get("style_centroid")
    if c is not None and len(c):
        return c
    refs = payload.get("style_refs") or []
    return style_centroid(refs) if refs else None


def _store_candidate(ctx: _Ctx, prefix: str, tag: str, png: bytes) -> tuple[str, str, int, int]:
    im = load_image(png)
    key = ctx.put(f"{prefix}/{tag}.png", png, "image/png")
    tkey = ctx.put(f"{prefix}/{tag}.webp", _thumb(png), "image/webp")
    return key, tkey, im.width, im.height


# ----------------------------------------------------------------------------- generate
def run_generate(payload: dict, ctx: Any) -> dict:
    c = _Ctx(ctx)
    t0 = time.time()
    style = payload.get("style_guide") or {}
    symbols = list(payload.get("symbols") or [])
    prompt_full = assemble_generate(style, payload.get("position_title"), symbols, payload.get("prompt_user"))
    provider = get_provider(payload.get("provider"))
    n = max(1, min(4, int(payload.get("n") or 1)))
    seed = payload.get("seed")
    refs = [_bytes(r) for r in (payload.get("style_refs") or [])][:3]
    c.progress(0.1, f"generating with {provider.name}")
    exemplars = [{**_exemplar_of(s), "placement": s.get("placement"), "region": s.get("region")} for s in symbols]
    try:
        result = provider.generate(prompt_full, style_refs=refs, aspect=payload.get("aspect") or style.get("aspect") or "2.75x4.75",
                                   n=n, seed=seed, symbol_exemplars=exemplars, style_guide=style, negative_prompt=style.get("negative_prompt"))
    except ProviderBlocked as e:
        return {"blocked": True, "reason": e.reason, "provider": provider.name, "model": provider.model, "prompt_full": prompt_full, "candidates": []}
    centroid = _centroid(payload)
    registry = payload.get("registry") or [{"symbol_id": s.get("symbol_id"), "name": s.get("name"), "gloss": s.get("gloss")} for s in symbols]
    declared = [{"symbol_id": s.get("symbol_id"), "placement": s.get("placement"), "region": s.get("region")} for s in symbols]
    prefix = payload.get("storage_prefix") or "tmp/generate"
    out = []
    for i, png in enumerate(result.images):
        c.progress(0.3 + 0.6 * (i + 1) / len(result.images), f"scoring candidate {i + 1}")
        key, tkey, w, h = _store_candidate(c, prefix, f"cand_{i}", png)
        rec = reconcile(declared, detect_symbols(png, registry, declared))
        out.append({"index": i, "image_key": key, "thumb_key": tkey, "width": w, "height": h,
                    "style_score": style_score(png, centroid), **rec})
    c.progress(1.0, "done")
    return {"candidates": out, "provider": result.provider, "model": result.model, "seed": result.seed, "prompt_full": prompt_full,
            "cost_estimate": result.cost_estimate, "elapsed_s": round(time.time() - t0, 2), "image_embed_backend": image_embed_backend()}


# ----------------------------------------------------------------------------- edit
def _declared_after(op: str, declared: list[dict], symbol: Optional[dict], to_symbol: Optional[dict], region, placement) -> list[dict]:
    sid = (symbol or {}).get("symbol_id")
    tid = (to_symbol or {}).get("symbol_id")
    out = [dict(d) for d in declared]
    if op == "add" and sid and all(d.get("symbol_id") != sid for d in out):
        out.append({"symbol_id": sid, "placement": placement, "region": region})
    elif op == "remove" and sid:
        out = [d for d in out if d.get("symbol_id") != sid]
    elif op == "replace" and sid and tid:
        out = [({**d, "symbol_id": tid} if d.get("symbol_id") == sid else d) for d in out]
        if all(d.get("symbol_id") != tid for d in out):
            out.append({"symbol_id": tid, "placement": placement, "region": region})
    elif op == "reposition" and sid:
        for d in out:
            if d.get("symbol_id") == sid:
                d["region"] = region
                d["placement"] = None
    return out


def run_edit(payload: dict, ctx: Any) -> dict:
    c = _Ctx(ctx)
    t0 = time.time()
    op = payload.get("op") or "cosmetic"
    if op not in EXPERIMENT_OPS and op != "cosmetic":
        raise ValueError(f"unknown op {op!r}")
    base = _bytes(payload.get("base_image"))
    if base is None:
        raise ValueError("base_image is required")
    symbol = payload.get("symbol") or {}
    to_symbol = payload.get("to_symbol")
    placement = payload.get("placement") or symbol.get("placement")
    region = payload.get("region")
    if op == "reposition":
        region_src = region or (zone(placement) if placement else zone("center"))
        target = payload.get("target_region") or zone(payload.get("target_placement") or "top")
        expected = _union(region_src, target)
    elif op == "cosmetic":
        region_src, target, expected = None, None, None
    else:
        region_src = region or zone(placement if placement and placement != "any" else "center")
        target, expected = None, region_src
    registry = payload.get("registry") or []
    allowed = [x.get("name") for x in (symbol, to_symbol or {}) if x and x.get("name")]
    how = validate_how_text(payload.get("how_text"), allowed, [r.get("name") for r in registry]) if op != "cosmetic" else strip_denylist(payload.get("how_text"))
    prompt_full = assemble_edit(op, symbol, to_symbol, (region if region else placement) if op != "reposition" else target, how)
    provider = get_provider(payload.get("provider"))
    n = max(1, min(4, int(payload.get("n") or 1)))
    seed = payload.get("seed")
    threshold = float(payload.get("fidelity_threshold", 0.85))
    refs = [_bytes(r) for r in (payload.get("style_refs") or [])][:3]
    centroid = _centroid(payload)
    declared = list(payload.get("declared") or [])
    declared_after = _declared_after(op, declared, symbol, to_symbol, region_src if op != "reposition" else target, placement)
    prefix = payload.get("storage_prefix") or "tmp/edit"
    base_im = load_image(base)
    extras = {"op": op, "region": region_src, "target_region": target, "exemplar": _exemplar_of(symbol),
              "to_exemplar": _exemplar_of(to_symbol) if to_symbol else None, "strength": float(payload.get("strength", 1.0)),
              "symbol_name": symbol.get("name")}

    attempts = [("medium", None, prompt_full, 1.0)]
    if op != "cosmetic":
        mask_png = png_bytes(mask_from_region(expected, base_im.width, base_im.height).convert("RGB"))
        attempts.append(("high", mask_png, prompt_full, 1.0))
        attempts.append(("high", mask_png, prompt_full + " Make the change as small as possible.", 0.6))
    candidates: list[dict] = []
    retries = 0
    blocked = None
    for attempt, (preserve, mask, prompt, strength) in enumerate(attempts):
        c.progress(0.1 + 0.25 * attempt, f"attempt {attempt + 1} ({preserve})")
        try:
            result = provider.edit(base, prompt, mask=mask, style_refs=refs, preserve=preserve, n=n, seed=seed,
                                   **{**extras, "strength": extras["strength"] * strength})
        except ProviderBlocked as e:
            blocked = e.reason
            break
        for i, png in enumerate(result.images):
            tag = f"a{attempt}_c{i}"
            key, tkey, w, h = _store_candidate(c, prefix, tag, png)
            heat_key = c.put(f"{prefix}/{tag}_heat.png", diff_heatmap(base, png), "image/png")
            fid = fidelity_of(base, png, expected)
            rec = reconcile(declared_after, detect_symbols(png, registry, declared_after))
            candidates.append({"index": len(candidates), "attempt": attempt, "preserve": preserve, "image_key": key, "thumb_key": tkey,
                               "heatmap_key": heat_key, "width": w, "height": h, "fidelity": fid["fidelity"], "embed_cos": fid["embed_cos"],
                               "ssim_out": fid["ssim_out"], "containment": fid["containment"], "style_score": style_score(png, centroid),
                               "below_threshold": bool(fid["fidelity"] < threshold), **rec})
        best = max((cd["fidelity"] for cd in candidates), default=0.0)
        if op == "cosmetic" or best >= threshold:
            break
        retries += 1
    c.progress(1.0, "done")
    candidates.sort(key=lambda cd: (-cd["fidelity"], cd["attempt"], cd["index"]))
    return {"candidates": candidates, "provider": provider.name, "model": provider.model, "seed": seed, "prompt_full": prompt_full,
            "retries": retries, "blocked": blocked, "op": op, "counts_as_experiment": op in EXPERIMENT_OPS,
            "expected_region": expected, "declared_after": declared_after, "fidelity_threshold": threshold,
            "elapsed_s": round(time.time() - t0, 2), "image_embed_backend": image_embed_backend()}


def _union(a: dict, b: dict) -> dict:
    x0, y0 = min(a["x"], b["x"]), min(a["y"], b["y"])
    x1, y1 = max(a["x"] + a["w"], b["x"] + b["w"]), max(a["y"] + a["h"], b["y"] + b["h"])
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


# ----------------------------------------------------------------------------- symbol + tag
def run_symbol(payload: dict, ctx: Any) -> dict:
    """payload: {provider?, name, gloss, prompt_user?, style_guide?, n, seed?, exemplar_bytes?|exemplar_path?, storage_prefix}"""
    c = _Ctx(ctx)
    style = payload.get("style_guide") or {}
    name, gloss = payload.get("name") or "symbol", payload.get("gloss") or ""
    prompt_full = f"{style.get('prompt_prefix', '')} Single symbol: {name} — {gloss}. {strip_denylist(payload.get('prompt_user'))}".strip()
    prompt_full += " One subject, white background, no text, no border."
    provider = get_provider(payload.get("provider"))
    try:
        result = provider.symbol(prompt_full, n=max(1, min(4, int(payload.get("n") or 1))), exemplar=_exemplar_of(payload), name=name,
                                 seed=payload.get("seed"))
    except ProviderBlocked as e:
        return {"blocked": True, "reason": e.reason, "candidates": [], "prompt_full": prompt_full}
    prefix = payload.get("storage_prefix") or "tmp/symbol"
    out = []
    for i, png in enumerate(result.images):
        key, tkey, w, h = _store_candidate(c, prefix, f"sym_{i}", png)
        out.append({"index": i, "image_key": key, "thumb_key": tkey, "width": w, "height": h})
    c.progress(1.0, "done")
    return {"candidates": out, "provider": result.provider, "model": result.model, "prompt_full": prompt_full}


def run_tag(payload: dict, ctx: Any = None) -> dict:
    """payload: {image: bytes|path, registry: [...], declared: [...]} → symbols_detected / missing / also_detected."""
    img = _bytes(payload.get("image"))
    if img is None:
        raise ValueError("image is required")
    declared = list(payload.get("declared") or [])
    return reconcile(declared, detect_symbols(img, payload.get("registry") or [], declared))

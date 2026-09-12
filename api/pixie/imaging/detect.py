"""Symbol detection (spec §6.5): a vision tagger returns which registry symbols are visibly present, with
salience and bbox; the result is reconciled with the declared symbols. The tagger never scores transmission."""
from __future__ import annotations

import base64
import json
import os
from typing import Any, Optional, Sequence

from .providers.base import ZONES, load_image, zone

PLACEMENT_SALIENCE = {"center": 1.0, "top": 0.7, "bottom": 0.7, "left": 0.5, "right": 0.5, "any": 0.6}
DECLARED_ONLY_SALIENCE = 0.3


def _sid(s: dict) -> str:
    return s.get("symbol_id") or s.get("id") or s.get("key") or ""


def detect_backend() -> str:
    if os.environ.get("PIXIE_DETECT", "").lower() == "fallback":
        return "declared_only"
    return "gemini" if os.environ.get("GEMINI_API_KEY") else "declared_only"


def _fallback(declared: Sequence[dict]) -> list[dict]:
    out = []
    for d in declared or []:
        placement = d.get("placement") or "any"
        region = d.get("region") or zone(placement)
        out.append({"symbol_id": _sid(d), "present": True, "salience": PLACEMENT_SALIENCE.get(placement, 0.6),
                    "bbox": region, "tagged_by": "declared_only"})
    return out


def _gemini(image_bytes: bytes, registry: Sequence[dict]) -> list[dict]:
    import httpx

    key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("GEMINI_VISION_MODEL", "gemini-2.5-flash")
    vocab = [{"symbol_id": _sid(s), "name": s.get("name"), "gloss": s.get("gloss")} for s in registry]
    prompt = ("You tag symbols on a card image. Vocabulary (only these ids may be returned): "
              + json.dumps(vocab, ensure_ascii=False)
              + ". Return a JSON array of {symbol_id, present (bool), salience (0..1, how much visual attention it takes), "
                "bbox ({x,y,w,h} in 0..1 of the image) } for every vocabulary entry that is visibly present. Nothing else.")
    body = {
        "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(image_bytes).decode()}}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = httpx.post(url, json=body, headers={"x-goog-api-key": key}, timeout=45.0)  # header auth works for every key type
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    items = json.loads(text)
    known = {_sid(s) for s in registry}
    out = []
    for it in items if isinstance(items, list) else []:
        sid = it.get("symbol_id")
        if sid in known and it.get("present", True):
            sal = float(it.get("salience", 0.5))
            out.append({"symbol_id": sid, "present": True, "salience": max(0.0, min(1.0, sal)), "bbox": it.get("bbox"), "tagged_by": "vision"})
    return out


def detect_symbols(image_bytes: Any, registry_symbols: Sequence[dict], declared: Optional[Sequence[dict]] = None) -> list[dict]:
    """[{symbol_id, present, salience, bbox|None, tagged_by}] — Gemini when keyed, else the declared-only fallback."""
    declared = list(declared or [])
    if detect_backend() == "gemini":
        try:
            img = load_image(image_bytes)
            import io

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return _gemini(buf.getvalue(), registry_symbols)
        except Exception as e:
            print(f"[imaging] vision tagger failed ({type(e).__name__}: {e}); declared-only fallback")
    return _fallback(declared)


def reconcile(declared: Sequence[dict], detected: Sequence[dict]) -> dict:
    """spec §6.5: declared∧detected → detector salience; declared∧¬detected → 0.3 `declared_only` (listed in
    symbols_missing until a human confirms); detected∧¬declared → kept (it is visible) and suggested in also_detected."""
    dec = {_sid(d): d for d in declared or [] if _sid(d)}
    det = {d["symbol_id"]: d for d in detected or [] if d.get("present", True)}
    symbols_detected, missing, also = [], [], []
    for sid, d in dec.items():
        if sid in det:
            x = det[sid]
            symbols_detected.append({"symbol_id": sid, "salience": float(x.get("salience", 0.6)), "bbox": x.get("bbox"),
                                     "tagged_by": x.get("tagged_by", "vision")})
        else:
            symbols_detected.append({"symbol_id": sid, "salience": DECLARED_ONLY_SALIENCE, "bbox": d.get("region") or zone(d.get("placement")),
                                     "tagged_by": "declared_only"})
            missing.append(sid)
    for sid, x in det.items():
        if sid not in dec:
            symbols_detected.append({"symbol_id": sid, "salience": float(x.get("salience", 0.5)), "bbox": x.get("bbox"),
                                     "tagged_by": x.get("tagged_by", "vision")})
            also.append(sid)
    return {"symbols_detected": symbols_detected, "symbols_missing": missing, "also_detected": also, "backend": detect_backend()}

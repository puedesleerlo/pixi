"""GeminiImageProvider — image + text → image over the REST generateContent endpoint.
Base image first (edits), style references after, prompt last. Safety blocks → ProviderBlocked.
Requires GEMINI_API_KEY; model id from GEMINI_IMAGE_MODEL (default gemini-2.5-flash-image). Never called in tests."""
from __future__ import annotations

import base64
import os
from typing import Any, Optional, Sequence

from .base import ProviderBlocked, ProviderResult, ProviderUnavailable, load_image, png_bytes

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
COST_PER_IMAGE = 0.04


def _inline(img: bytes, mime: str = "image/png") -> dict:
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(img).decode()}}


class GeminiImageProvider:
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model or os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
        if not self.api_key:
            raise ProviderUnavailable("GEMINI_API_KEY is not set")

    def _call(self, parts: list[dict], n: int, seed: Optional[int]) -> ProviderResult:
        import httpx

        images: list[bytes] = []
        last_err: Optional[Exception] = None
        for k in range(max(1, n)):
            body: dict[str, Any] = {"contents": [{"parts": parts}], "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}}
            if seed is not None:
                body["generationConfig"]["seed"] = int(seed) + k
            try:
                r = httpx.post(ENDPOINT.format(model=self.model), params={"key": self.api_key}, json=body, timeout=90.0)
            except Exception as e:
                raise ProviderUnavailable(f"gemini request failed: {e}") from e
            if r.status_code in (429, 503):
                raise ProviderUnavailable(f"gemini {r.status_code}: {r.text[:200]}")
            if r.status_code >= 400:
                raise ProviderUnavailable(f"gemini {r.status_code}: {r.text[:200]}")
            data = r.json()
            fb = data.get("promptFeedback") or {}
            if fb.get("blockReason"):
                raise ProviderBlocked(str(fb.get("blockReason")))
            cands = data.get("candidates") or []
            if not cands:
                raise ProviderBlocked("no candidates returned")
            if cands[0].get("finishReason") in ("SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT"):
                raise ProviderBlocked(str(cands[0].get("finishReason")))
            found = False
            for part in cands[0].get("content", {}).get("parts", []):
                inline = part.get("inline_data") or part.get("inlineData")
                if inline and inline.get("data"):
                    raw = base64.b64decode(inline["data"])
                    images.append(png_bytes(load_image(raw)))
                    found = True
                    break
            if not found:
                last_err = ProviderUnavailable("gemini returned no image part")
        if not images:
            raise last_err or ProviderUnavailable("gemini returned nothing")
        return ProviderResult(images=images, provider=self.name, model=self.model, seed=seed, cost_estimate=COST_PER_IMAGE * len(images))

    def generate(self, prompt_full: str, style_refs: Sequence[bytes] = (), aspect: str = "2.75x4.75", n: int = 1,
                 seed: Optional[int] = None, **extras: Any) -> ProviderResult:
        parts: list[dict] = [_inline(png_bytes(load_image(ref))) for ref in list(style_refs)[:3]]
        text = prompt_full
        if style_refs:
            text = "Use the attached images only as style references. " + text
        text += f" Aspect ratio {aspect.replace('x', ':')}."
        if extras.get("negative_prompt"):
            text += f" Avoid: {extras['negative_prompt']}."
        parts.append({"text": text})
        return self._call(parts, n, seed)

    def edit(self, image: bytes, prompt_full: str, mask: Optional[bytes] = None, style_refs: Sequence[bytes] = (),
             preserve: str = "medium", n: int = 1, seed: Optional[int] = None, **extras: Any) -> ProviderResult:
        parts: list[dict] = [_inline(png_bytes(load_image(image)))]
        text = prompt_full
        if mask is not None:
            parts.append(_inline(png_bytes(load_image(mask))))
            text += " The second image is a mask: white marks the only area that may change."
        for ref in list(style_refs)[:2]:
            parts.append(_inline(png_bytes(load_image(ref))))
        if preserve == "high":
            text += " Preserve every pixel outside the requested change as exactly as possible."
        parts.append({"text": text})
        return self._call(parts, n, seed)

    def symbol(self, prompt_full: str, n: int = 1, **extras: Any) -> ProviderResult:
        text = prompt_full + " Single subject on a plain white background, no text, no border, square."
        return self._call([{"text": text}], n, extras.get("seed"))

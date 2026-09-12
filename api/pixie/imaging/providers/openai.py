"""OpenAI Images (generations + edits with an optional mask). Requires OPENAI_API_KEY. Never called in tests."""
from __future__ import annotations

import base64
import io
import os
from typing import Any, Optional, Sequence

from .base import ProviderBlocked, ProviderResult, ProviderUnavailable, load_image, png_bytes

BASE = "https://api.openai.com/v1"
COST_PER_IMAGE = 0.04


class OpenAIImageProvider:
    name = "openai"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model or os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
        if not self.api_key:
            raise ProviderUnavailable("OPENAI_API_KEY is not set")

    def _images_from(self, r) -> list[bytes]:
        if r.status_code == 400 and "safety" in r.text.lower():
            raise ProviderBlocked(r.text[:200])
        if r.status_code >= 400:
            raise ProviderUnavailable(f"openai {r.status_code}: {r.text[:200]}")
        out = []
        for d in r.json().get("data", []):
            if d.get("b64_json"):
                out.append(png_bytes(load_image(base64.b64decode(d["b64_json"]))))
        if not out:
            raise ProviderUnavailable("openai returned no image")
        return out

    def generate(self, prompt_full: str, style_refs: Sequence[bytes] = (), aspect: str = "2.75x4.75", n: int = 1,
                 seed: Optional[int] = None, **extras: Any) -> ProviderResult:
        import httpx

        size = "1024x1536" if aspect != "1x1" else "1024x1024"
        r = httpx.post(f"{BASE}/images/generations", headers={"Authorization": f"Bearer {self.api_key}"},
                       json={"model": self.model, "prompt": prompt_full, "n": max(1, n), "size": size}, timeout=120.0)
        imgs = self._images_from(r)
        return ProviderResult(images=imgs, provider=self.name, model=self.model, seed=None, cost_estimate=COST_PER_IMAGE * len(imgs))

    def edit(self, image: bytes, prompt_full: str, mask: Optional[bytes] = None, style_refs: Sequence[bytes] = (),
             preserve: str = "medium", n: int = 1, seed: Optional[int] = None, **extras: Any) -> ProviderResult:
        import httpx

        files: dict[str, Any] = {"image": ("base.png", png_bytes(load_image(image)), "image/png")}
        if mask is not None:
            # OpenAI masks: transparent = editable. Convert our white-inside mask to alpha.
            m = load_image(mask).convert("L")
            rgba = load_image(image).convert("RGBA")
            alpha = m.point(lambda v: 255 - v)
            rgba.putalpha(alpha)
            buf = io.BytesIO()
            rgba.save(buf, format="PNG")
            files["mask"] = ("mask.png", buf.getvalue(), "image/png")
        data = {"model": self.model, "prompt": prompt_full, "n": str(max(1, n))}
        r = httpx.post(f"{BASE}/images/edits", headers={"Authorization": f"Bearer {self.api_key}"}, data=data, files=files, timeout=120.0)
        imgs = self._images_from(r)
        return ProviderResult(images=imgs, provider=self.name, model=self.model, seed=None, cost_estimate=COST_PER_IMAGE * len(imgs))

    def symbol(self, prompt_full: str, n: int = 1, **extras: Any) -> ProviderResult:
        return self.generate(prompt_full + " Single subject on a plain white background, no text.", aspect="1x1", n=n)

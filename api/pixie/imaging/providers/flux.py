"""FLUX.1 Kontext (Black Forest Labs) — in-context, reference-preserving edits. Requires BFL_API_KEY.
Minimal adapter over the public HTTP API (submit → poll). Never called in tests."""
from __future__ import annotations

import base64
import os
import time
from typing import Any, Optional, Sequence

from .base import ProviderBlocked, ProviderResult, ProviderUnavailable, load_image, png_bytes

BASE = "https://api.bfl.ml/v1"
COST_PER_IMAGE = 0.04


class FluxKontextProvider:
    name = "flux"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.environ.get("BFL_API_KEY")
        self.model = model or os.environ.get("BFL_MODEL", "flux-kontext-pro")
        if not self.api_key:
            raise ProviderUnavailable("BFL_API_KEY is not set")

    def _submit_and_poll(self, body: dict, n: int, seed: Optional[int]) -> ProviderResult:
        import httpx

        images: list[bytes] = []
        for k in range(max(1, n)):
            b = dict(body)
            if seed is not None:
                b["seed"] = int(seed) + k
            r = httpx.post(f"{BASE}/{self.model}", headers={"x-key": self.api_key}, json=b, timeout=60.0)
            if r.status_code >= 400:
                raise ProviderUnavailable(f"flux {r.status_code}: {r.text[:200]}")
            task_id = r.json().get("id")
            for _ in range(90):
                time.sleep(1.0)
                p = httpx.get(f"{BASE}/get_result", headers={"x-key": self.api_key}, params={"id": task_id}, timeout=30.0).json()
                status = p.get("status")
                if status == "Ready":
                    url = (p.get("result") or {}).get("sample")
                    img = httpx.get(url, timeout=60.0).content
                    images.append(png_bytes(load_image(img)))
                    break
                if status in ("Content Moderated", "Request Moderated"):
                    raise ProviderBlocked(status)
                if status in ("Error", "Task not found"):
                    raise ProviderUnavailable(f"flux: {status}")
            else:
                raise ProviderUnavailable("flux: timed out")
        return ProviderResult(images=images, provider=self.name, model=self.model, seed=seed, cost_estimate=COST_PER_IMAGE * len(images))

    def generate(self, prompt_full: str, style_refs: Sequence[bytes] = (), aspect: str = "2.75x4.75", n: int = 1,
                 seed: Optional[int] = None, **extras: Any) -> ProviderResult:
        body: dict[str, Any] = {"prompt": prompt_full, "aspect_ratio": aspect.replace("x", ":"), "output_format": "png"}
        if style_refs:
            body["input_image"] = base64.b64encode(png_bytes(load_image(style_refs[0]))).decode()
        return self._submit_and_poll(body, n, seed)

    def edit(self, image: bytes, prompt_full: str, mask: Optional[bytes] = None, style_refs: Sequence[bytes] = (),
             preserve: str = "medium", n: int = 1, seed: Optional[int] = None, **extras: Any) -> ProviderResult:
        body = {"prompt": prompt_full + (" Keep everything else exactly as it is." if preserve == "high" else ""),
                "input_image": base64.b64encode(png_bytes(load_image(image))).decode(), "output_format": "png"}
        return self._submit_and_poll(body, n, seed)

    def symbol(self, prompt_full: str, n: int = 1, **extras: Any) -> ProviderResult:
        body = {"prompt": prompt_full + " Single subject on a plain white background, no text, square.", "aspect_ratio": "1:1", "output_format": "png"}
        return self._submit_and_poll(body, n, extras.get("seed"))

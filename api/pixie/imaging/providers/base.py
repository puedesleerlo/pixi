"""Provider protocol (spec §6.1), regions and placement zones (contract §8), provider selection."""
from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Sequence

from PIL import Image, ImageDraw, ImageFilter

# placement zones in 0..1 of the image: x, y, w, h  (contract §8)
ZONES: dict[str, tuple[float, float, float, float]] = {
    "center": (0.24, 0.30, 0.52, 0.40),
    "top": (0.30, 0.04, 0.40, 0.22),
    "bottom": (0.30, 0.74, 0.40, 0.22),
    "left": (0.02, 0.30, 0.22, 0.40),
    "right": (0.76, 0.30, 0.22, 0.40),
    "any": (0.0, 0.0, 1.0, 1.0),
}
ZONE_ORDER = ["center", "top", "bottom", "left", "right"]

# aspect → pixel size of a generated card
ASPECTS: dict[str, tuple[int, int]] = {"2.75x4.75": (550, 950), "1x1.7": (560, 952), "custom": (550, 950)}


class ProviderUnavailable(Exception):
    """The provider cannot be used (no key, no network, unsupported operation)."""


class ProviderBlocked(Exception):
    """The provider refused the request (safety); `reason` is logged, nothing is charged."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class ProviderResult:
    images: list[bytes]                 # PNG bytes, one per candidate
    provider: str
    model: str
    seed: Optional[int] = None
    cost_estimate: float = 0.0          # USD, rough
    meta: dict[str, Any] = field(default_factory=dict)


class ImageProvider(Protocol):
    name: str
    model: str

    def generate(self, prompt_full: str, style_refs: Sequence[bytes] = (), aspect: str = "2.75x4.75", n: int = 1,
                 seed: Optional[int] = None, **extras: Any) -> ProviderResult: ...

    def edit(self, image: bytes, prompt_full: str, mask: Optional[bytes] = None, style_refs: Sequence[bytes] = (),
             preserve: str = "medium", n: int = 1, seed: Optional[int] = None, **extras: Any) -> ProviderResult: ...

    def symbol(self, prompt_full: str, n: int = 1, **extras: Any) -> ProviderResult: ...


# ----------------------------------------------------------------------------- regions
def zone(placement: Optional[str]) -> dict:
    """Placement name → region dict {x, y, w, h} in 0..1. Unknown/None → whole image."""
    x, y, w, h = ZONES.get(placement or "any", ZONES["any"])
    return {"x": x, "y": y, "w": w, "h": h}


def region_to_box(region: Optional[dict], width: int, height: int) -> tuple[int, int, int, int]:
    """Region {x,y,w,h} in 0..1 → integer pixel box (x0, y0, x1, y1), clipped to the image."""
    if not region:
        return 0, 0, width, height
    x0 = int(round(float(region["x"]) * width))
    y0 = int(round(float(region["y"]) * height))
    x1 = int(round((float(region["x"]) + float(region["w"])) * width))
    y1 = int(round((float(region["y"]) + float(region["h"])) * height))
    x0, y0 = max(0, min(width - 1, x0)), max(0, min(height - 1, y0))
    x1, y1 = max(x0 + 1, min(width, x1)), max(y0 + 1, min(height, y1))
    return x0, y0, x1, y1


def mask_from_region(region: Optional[dict], width: int, height: int, feather: int = 0) -> Image.Image:
    """'L' mask, 255 inside the region, optionally feathered *inward* so nothing outside the box is touched."""
    m = Image.new("L", (width, height), 0)
    x0, y0, x1, y1 = region_to_box(region, width, height)
    d = ImageDraw.Draw(m)
    if feather > 0 and (x1 - x0) > 2 * feather + 2 and (y1 - y0) > 2 * feather + 2:
        inner = Image.new("L", (x1 - x0, y1 - y0), 0)
        ImageDraw.Draw(inner).rounded_rectangle([feather, feather, x1 - x0 - 1 - feather, y1 - y0 - 1 - feather],
                                                radius=feather, fill=255)
        inner = inner.filter(ImageFilter.GaussianBlur(feather / 2))
        m.paste(inner, (x0, y0))
    else:
        d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=255)
    return m


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def load_image(x: Any) -> Image.Image:
    """bytes | path | PIL.Image → RGB PIL image."""
    if isinstance(x, Image.Image):
        return x.convert("RGB")
    if isinstance(x, (bytes, bytearray)):
        return Image.open(io.BytesIO(bytes(x))).convert("RGB")
    if isinstance(x, str):
        return Image.open(x).convert("RGB")
    raise TypeError(f"cannot load image from {type(x).__name__}")


# ----------------------------------------------------------------------------- selection
def provider_name_from_env() -> str:
    forced = os.environ.get("PIXIE_IMAGE_PROVIDER")
    if forced:
        return forced
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("BFL_API_KEY"):
        return "flux"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "local"


def get_provider(name: Optional[str] = None) -> ImageProvider:
    """Provider by name or by environment (contract §2). The local collage provider always works."""
    name = (name or provider_name_from_env()).lower()
    if name == "local":
        from .local import LocalCollageProvider

        return LocalCollageProvider()
    if name == "gemini":
        from .gemini import GeminiImageProvider

        return GeminiImageProvider()
    if name == "flux":
        from .flux import FluxKontextProvider

        return FluxKontextProvider()
    if name == "openai":
        from .openai import OpenAIImageProvider

        return OpenAIImageProvider()
    raise ProviderUnavailable(f"unknown image provider {name!r}")

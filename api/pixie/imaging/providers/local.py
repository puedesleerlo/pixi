"""LocalCollageProvider — always available. Composes cards from symbol exemplar crops and performs
region-confined edits with Pillow. Everything outside the edited region stays byte-identical, which is the
property the fidelity metrics measure. Deterministic for a given seed."""
from __future__ import annotations

import hashlib
import io
from typing import Any, Optional, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .base import ASPECTS, ZONE_ORDER, ProviderResult, load_image, mask_from_region, png_bytes, region_to_box, zone

PAPER = "#f4efe6"
INK = "#141414"


def _seed_int(seed: Optional[int], salt: str = "") -> int:
    if seed is None:
        seed = 0
    return int(hashlib.sha256(f"{seed}:{salt}".encode()).hexdigest()[:8], 16)


def _hex_ok(c: Any) -> bool:
    return isinstance(c, str) and len(c) == 7 and c.startswith("#")


def _fit(img: Image.Image, box_w: int, box_h: int, scale: float = 1.0) -> Image.Image:
    """Resize to fit inside (box_w, box_h) keeping aspect, scaled by `scale` (≤ box)."""
    bw, bh = max(1, int(box_w * scale)), max(1, int(box_h * scale))
    im = img.copy()
    im.thumbnail((bw, bh), Image.LANCZOS)
    return im


def _soft_mask(size: tuple[int, int], feather: int) -> Image.Image:
    """Feathered rounded-rectangle alpha for a pasted crop; the feather is inward so the crop's bounds hold."""
    w, h = size
    m = Image.new("L", (w, h), 0)
    f = max(0, min(feather, (min(w, h) - 2) // 2))
    ImageDraw.Draw(m).rounded_rectangle([f, f, w - 1 - f, h - 1 - f], radius=max(2, f), fill=255)
    if f > 0:
        m = m.filter(ImageFilter.GaussianBlur(f / 2))
    return m


def _ring_median(img: Image.Image, box: tuple[int, int, int, int], ring: int) -> tuple[int, int, int]:
    """Median colour of a ring of `ring` px around the box (inside the image), used to fill removed regions."""
    x0, y0, x1, y1 = box
    a = np.asarray(img)
    H, W = a.shape[:2]
    X0, Y0, X1, Y1 = max(0, x0 - ring), max(0, y0 - ring), min(W, x1 + ring), min(H, y1 + ring)
    outer = a[Y0:Y1, X0:X1].reshape(-1, 3)
    inner = a[y0:y1, x0:x1].reshape(-1, 3)
    if len(outer) > len(inner):
        # subtract the inner block: build a boolean mask over the outer window
        mask = np.ones((Y1 - Y0, X1 - X0), dtype=bool)
        mask[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0] = False
        ring_px = a[Y0:Y1, X0:X1][mask]
        if len(ring_px):
            med = np.median(ring_px, axis=0)
            return tuple(int(v) for v in med)
    med = np.median(inner, axis=0) if len(inner) else np.array([244, 239, 230])
    return tuple(int(v) for v in med)


def _fill_region(img: Image.Image, box: tuple[int, int, int, int], seed: int, feather: int, noise: float = 3.0) -> Image.Image:
    """Return a copy with the box filled by the surround's median colour plus light noise, feathered at the edges."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    colour = _ring_median(img, box, ring=max(4, int(0.06 * max(w, h))))
    rng = np.random.default_rng(seed)
    patch = np.empty((h, w, 3), dtype=np.float32)
    patch[:] = np.array(colour, dtype=np.float32)
    patch += rng.normal(0.0, noise, size=patch.shape)
    patch = np.clip(patch, 0, 255).astype(np.uint8)
    fill = Image.fromarray(patch, "RGB")
    out = img.copy()
    out.paste(fill, (x0, y0), _soft_mask((w, h), feather))
    return out


def _paste_exemplar(img: Image.Image, exemplar: Image.Image, box: tuple[int, int, int, int], seed: int, feather: int,
                    scale: float = 0.92, jitter: float = 0.02, ink: bool = False) -> Image.Image:
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    ex = _fit(exemplar, w, h, scale)
    if ink:
        ex = ImageOps.autocontrast(ImageOps.grayscale(ex)).convert("RGB")
    rng = np.random.default_rng(seed)
    jx = int(rng.uniform(-jitter, jitter) * w)
    jy = int(rng.uniform(-jitter, jitter) * h)
    px = x0 + (w - ex.width) // 2 + jx
    py = y0 + (h - ex.height) // 2 + jy
    # keep the crop fully inside the region box so nothing outside changes
    px = max(x0, min(x1 - ex.width, px))
    py = max(y0, min(y1 - ex.height, py))
    out = img.copy()
    out.paste(ex, (px, py), _soft_mask(ex.size, feather))
    return out


def _exemplar_image(ex: dict) -> Optional[Image.Image]:
    for key in ("image_bytes", "image", "exemplar_bytes"):
        if ex.get(key) is not None:
            return load_image(ex[key])
    for key in ("path", "image_path", "exemplar_path"):
        if ex.get(key):
            return load_image(ex[key])
    return None


def _label_tile(text: str, size: tuple[int, int]) -> Image.Image:
    """A text tile used when a symbol has no exemplar image (the local provider cannot draw new art)."""
    w, h = size
    tile = Image.new("RGB", (w, h), "#efe8da")
    d = ImageDraw.Draw(tile)
    d.rectangle([1, 1, w - 2, h - 2], outline=INK, width=1)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia.ttf", max(12, h // 8))
    except Exception:
        font = ImageFont.load_default()
    words = (text or "symbol").upper()
    bbox = d.textbbox((0, 0), words, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((w - tw) // 2, (h - th) // 2), words, fill=INK, font=font)
    return tile


class LocalCollageProvider:
    name = "local"
    model = "collage-1"

    # ------------------------------------------------------------------ generate
    def generate(self, prompt_full: str, style_refs: Sequence[bytes] = (), aspect: str = "2.75x4.75", n: int = 1,
                 seed: Optional[int] = None, **extras: Any) -> ProviderResult:
        """extras: symbol_exemplars=[{symbol_id, name?, image_bytes|path, placement?|region?}], style_guide={palette, line, border}."""
        W, H = ASPECTS.get(aspect, ASPECTS["2.75x4.75"])
        style = extras.get("style_guide") or {}
        palette = [c for c in (style.get("palette") or []) if _hex_ok(c)]
        paper = palette[0] if palette else PAPER
        border = style.get("border") or {}
        border_colour = border.get("color") if _hex_ok(border.get("color")) else INK
        ink_mode = (style.get("line") == "ink")
        exemplars = list(extras.get("symbol_exemplars") or [])
        images: list[bytes] = []
        for i in range(max(1, n)):
            s = _seed_int(seed, f"gen:{i}")
            card = Image.new("RGB", (W, H), paper)
            d = ImageDraw.Draw(card)
            bw = max(4, W // 60)
            if border.get("style") != "none":
                d.rectangle([bw, bw, W - 1 - bw, H - 1 - bw], outline=border_colour, width=max(2, bw // 3))
            used: set[str] = set()
            for k, ex in enumerate(exemplars):
                region = ex.get("region")
                placement = ex.get("placement")
                if region is None:
                    if placement in (None, "any") or placement in used:
                        placement = next((z for z in ZONE_ORDER if z not in used), None) or "center"
                    used.add(placement)
                    region = zone(placement)
                box = region_to_box(region, W, H)
                im = _exemplar_image(ex)
                if im is None:
                    im = _label_tile(ex.get("name") or ex.get("symbol_id") or "symbol", (box[2] - box[0], box[3] - box[1]))
                card = _paste_exemplar(card, im, box, _seed_int(s, f"ex:{k}"), feather=max(3, W // 90), ink=ink_mode)
            images.append(png_bytes(card))
        return ProviderResult(images=images, provider=self.name, model=self.model, seed=seed, cost_estimate=0.0,
                              meta={"prompt_full": prompt_full, "aspect": aspect, "size": [W, H]})

    # ------------------------------------------------------------------ edit
    def edit(self, image: bytes, prompt_full: str, mask: Optional[bytes] = None, style_refs: Sequence[bytes] = (),
             preserve: str = "medium", n: int = 1, seed: Optional[int] = None, **extras: Any) -> ProviderResult:
        """extras: op, region {x,y,w,h} | placement, exemplar {image_bytes|path, name}, to_exemplar, target_region,
        strength (1.0), symbol_name. Only pixels inside the region (and, for reposition, the target region) change."""
        base = load_image(image)
        W, H = base.size
        op = extras.get("op") or "cosmetic"
        strength = float(extras.get("strength", 1.0))
        region = extras.get("region") or (zone(extras.get("placement")) if extras.get("placement") else None)
        feather = max(2, W // 120) if preserve == "high" else max(3, W // 80)
        images: list[bytes] = []
        for i in range(max(1, n)):
            s = _seed_int(seed, f"edit:{op}:{i}")
            out = base
            if op == "cosmetic":
                out = self._cosmetic(base, strength, s)
            else:
                if region is None:
                    region = zone("center")
                box = region_to_box(region, W, H)
                if op == "remove":
                    out = _fill_region(base, box, s, feather)
                elif op == "add":
                    out = self._add(base, extras.get("exemplar") or {}, box, s, feather)
                elif op == "replace":
                    cleared = _fill_region(base, box, s, feather)
                    out = self._add(cleared, extras.get("to_exemplar") or extras.get("exemplar") or {}, box, s, feather)
                elif op in ("emphasize", "deemphasize"):
                    out = self._emphasize(base, box, s, feather, up=(op == "emphasize"), strength=strength)
                elif op == "reposition":
                    target = extras.get("target_region") or zone(extras.get("target_placement") or "top")
                    tbox = region_to_box(target, W, H)
                    crop = base.crop(box)
                    cleared = _fill_region(base, box, s, feather)
                    out = _paste_exemplar(cleared, crop, tbox, s, feather, scale=0.98, jitter=0.0)
                else:
                    raise ValueError(f"unknown edit op {op!r}")
            images.append(png_bytes(out))
        return ProviderResult(images=images, provider=self.name, model=self.model, seed=seed, cost_estimate=0.0,
                              meta={"prompt_full": prompt_full, "op": op, "preserve": preserve, "region": region})

    def _add(self, base: Image.Image, exemplar: dict, box, s: int, feather: int) -> Image.Image:
        im = _exemplar_image(exemplar)
        if im is None:
            im = _label_tile(exemplar.get("name") or exemplar.get("symbol_id") or "symbol", (box[2] - box[0], box[3] - box[1]))
        return _paste_exemplar(base, im, box, s, feather)

    def _emphasize(self, base: Image.Image, box, s: int, feather: int, up: bool, strength: float) -> Image.Image:
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        crop = base.crop(box)
        factor = 1.0 + (0.15 if up else -0.13) * strength
        contrast = 1.0 + (0.10 if up else -0.10) * strength
        crop = ImageEnhance.Contrast(crop).enhance(contrast)
        nw, nh = max(1, int(w * factor)), max(1, int(h * factor))
        scaled = crop.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGB", (w, h), _ring_median(base, box, ring=max(4, int(0.06 * max(w, h)))))
        if up:
            # larger: crop the centre of the scaled content back to the box size
            ox, oy = (nw - w) // 2, (nh - h) // 2
            canvas = scaled.crop((ox, oy, ox + w, oy + h))
        else:
            canvas.paste(scaled, ((w - nw) // 2, (h - nh) // 2))
        out = base.copy()
        out.paste(canvas, (x0, y0), _soft_mask((w, h), feather))
        return out

    @staticmethod
    def _cosmetic(base: Image.Image, strength: float, s: int) -> Image.Image:
        """Whole-image lighting/tone/line-softening. strength 1 = mild; ≥ 2 also softens lines (a 'line cleanup')."""
        out = ImageEnhance.Brightness(base).enhance(1.0 + 0.06 * strength)
        out = ImageEnhance.Contrast(out).enhance(1.0 + 0.15 * strength)
        if strength >= 2.0:
            out = out.filter(ImageFilter.GaussianBlur(0.6 * strength))
        a = np.asarray(out).astype(np.int16)
        a[..., 0] = np.clip(a[..., 0] + int(8 * strength), 0, 255)
        a[..., 2] = np.clip(a[..., 2] - int(6 * strength), 0, 255)
        return Image.fromarray(a.astype(np.uint8), "RGB")

    # ------------------------------------------------------------------ symbol
    def symbol(self, prompt_full: str, n: int = 1, **extras: Any) -> ProviderResult:
        """Renders an exemplar (extras.exemplar) on white; without one, a labelled tile — the local provider draws no new art."""
        size = int(extras.get("size", 400))
        images = []
        for i in range(max(1, n)):
            canvas = Image.new("RGB", (size, size), "white")
            ex = _exemplar_image(extras.get("exemplar") or {})
            if ex is None:
                ex = _label_tile(extras.get("name") or prompt_full[:24], (size - 40, size - 40))
            im = _fit(ex, size - 40, size - 40)
            canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
            images.append(png_bytes(canvas))
        return ProviderResult(images=images, provider=self.name, model=self.model, seed=None, cost_estimate=0.0,
                              meta={"prompt_full": prompt_full})

"""Fidelity for edits — measured, not judged (spec §6.4).

embed_cos   cosine between image embeddings of base and candidate (CLIP ViT-B/32 when available, else perceptual)
ssim_out    SSIM between base and candidate outside the expected change region
containment share of blurred pixel-difference mass inside the region
fidelity    0.5 * clamp((embed_cos - 0.6) / 0.4) + 0.5 * ssim_out
"""
from __future__ import annotations

import io
import os
import threading
from typing import Any, Optional

import numpy as np
from PIL import Image, ImageFilter

from .providers.base import load_image, region_to_box

EMBED_DIM = 768
_clip_lock = threading.Lock()
_clip_model: Any = None
_clip_failed = False


def _want_backend() -> str:
    return (os.environ.get("PIXIE_IMAGE_EMBED") or "auto").lower()


def _load_clip():
    global _clip_model, _clip_failed
    with _clip_lock:
        if _clip_model is not None or _clip_failed:
            return _clip_model
        try:
            from sentence_transformers import SentenceTransformer

            _clip_model = SentenceTransformer("sentence-transformers/clip-ViT-B-32")
        except Exception as e:  # weights missing, no torch, no network
            print(f"[imaging] CLIP unavailable ({type(e).__name__}); perceptual embedding in use")
            _clip_failed = True
        return _clip_model


def image_embed_backend() -> str:
    b = _want_backend()
    if b == "perceptual":
        return "perceptual"
    if b in ("clip", "auto") and _load_clip() is not None:
        return "clip-vit-b32"
    return "perceptual"


def _perceptual(img: Image.Image) -> np.ndarray:
    """Deterministic perceptual embedding, deliberately *global* so a change confined to one placement zone
    moves it little while a whole-image change moves it a lot:
      8×8 luminance grid (64, mean-centred)        weight 0.35
      HSV histogram: 12 hue (saturation-weighted) + 6 sat + 6 value (24)   weight 1.0
      global gradient-orientation histogram, 16 bins, magnitude-weighted   weight 0.7
      4×4 grid of 8-bin gradient-orientation histograms (128)              weight 0.25
    Each block is L2-normalised, concatenated, padded to EMBED_DIM and L2-normalised again."""
    small = img.convert("RGB").resize((64, 64), Image.BILINEAR)
    g = np.asarray(small.convert("L"), dtype=np.float32) / 255.0
    lum = g.reshape(8, 8, 8, 8).mean(axis=(1, 3)).ravel()
    lum = lum - lum.mean()
    lum /= (np.linalg.norm(lum) + 1e-8)
    hsv = np.asarray(small.convert("HSV"), dtype=np.float32) / 255.0
    hue_hist = np.bincount(np.minimum((hsv[..., 0].ravel() * 12).astype(int), 11), weights=hsv[..., 1].ravel(), minlength=12)[:12]
    sat_hist = np.bincount(np.minimum((hsv[..., 1].ravel() * 6).astype(int), 5), minlength=6)[:6].astype(np.float32)
    val_hist = np.bincount(np.minimum((hsv[..., 2].ravel() * 6).astype(int), 5), minlength=6)[:6].astype(np.float32)
    col = np.concatenate([hue_hist, sat_hist, val_hist]).astype(np.float32)
    col /= (np.linalg.norm(col) + 1e-8)
    gy, gx = np.gradient(g)
    mag = np.hypot(gx, gy)
    ang = (np.arctan2(gy, gx) + np.pi) / (2 * np.pi)  # 0..1
    glob = np.bincount(np.minimum((ang.ravel() * 16).astype(int), 15), weights=mag.ravel(), minlength=16)[:16].astype(np.float32)
    glob /= (np.linalg.norm(glob) + 1e-8)
    bins = np.minimum((ang * 8).astype(int), 7)
    hist = np.zeros((4, 4, 8), dtype=np.float32)
    for cy in range(4):
        for cx in range(4):
            m = mag[cy * 16:(cy + 1) * 16, cx * 16:(cx + 1) * 16]
            b = bins[cy * 16:(cy + 1) * 16, cx * 16:(cx + 1) * 16]
            hist[cy, cx] = np.bincount(b.ravel(), weights=m.ravel(), minlength=8)[:8]
    grid = hist.ravel()
    grid /= (np.linalg.norm(grid) + 1e-8)
    # weights: spatial luminance is deliberately light (a symbol added in one zone must not dominate);
    # palette and global line statistics carry most of the 'same picture / same style' signal.
    vec = np.concatenate([lum * 0.35, col * 1.0, glob * 0.7, grid * 0.25]).astype(np.float32)
    out = np.zeros(EMBED_DIM, dtype=np.float32)
    out[: len(vec)] = vec
    return out / (np.linalg.norm(out) + 1e-8)


def image_embed(img: Any) -> np.ndarray:
    """Embedding (EMBED_DIM) of an image (bytes | path | PIL). CLIP when loadable, else perceptual."""
    im = load_image(img)
    if image_embed_backend() == "clip-vit-b32":
        vec = np.asarray(_clip_model.encode([im], convert_to_numpy=True, normalize_embeddings=True)[0], dtype=np.float32)
        out = np.zeros(EMBED_DIM, dtype=np.float32)
        out[: min(EMBED_DIM, len(vec))] = vec[:EMBED_DIM]
        return out / (np.linalg.norm(out) + 1e-8)
    return _perceptual(im)


def embed_cos(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, dtype=np.float64).ravel(), np.asarray(b, dtype=np.float64).ravel()
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))


# ----------------------------------------------------------------------------- pixel metrics
def _pair_gray(base: Any, cand: Any, max_side: int = 1024) -> tuple[np.ndarray, np.ndarray]:
    b = load_image(base)
    c = load_image(cand)
    if c.size != b.size:
        c = c.resize(b.size, Image.BILINEAR)
    scale = min(1.0, max_side / max(b.size))
    if scale < 1.0:
        size = (max(8, int(b.width * scale)), max(8, int(b.height * scale)))
        b, c = b.resize(size, Image.BILINEAR), c.resize(size, Image.BILINEAR)
    return (np.asarray(b.convert("L"), dtype=np.float64), np.asarray(c.convert("L"), dtype=np.float64))


def _region_mask(shape: tuple[int, int], region: Optional[dict]) -> np.ndarray:
    h, w = shape
    m = np.zeros((h, w), dtype=bool)
    if region is None:
        return m
    x0, y0, x1, y1 = region_to_box(region, w, h)
    m[y0:y1, x0:x1] = True
    return m


def ssim_out(base: Any, cand: Any, region: Optional[dict] = None) -> float:
    """Mean SSIM over pixels outside `region` (whole image when region is None). 1.0 = identical."""
    from skimage.metrics import structural_similarity

    gb, gc = _pair_gray(base, cand)
    if np.array_equal(gb, gc):
        return 1.0
    win = 7 if min(gb.shape) >= 7 else 3
    _, smap = structural_similarity(gb, gc, data_range=255.0, full=True, win_size=win)
    inside = _region_mask(gb.shape, region)
    outside = ~inside
    if region is None or outside.sum() == 0:
        return float(np.clip(smap.mean(), 0.0, 1.0))
    return float(np.clip(smap[outside].mean(), 0.0, 1.0))


def _blurred_absdiff(base: Any, cand: Any) -> np.ndarray:
    gb, gc = _pair_gray(base, cand)
    diff = np.abs(gb - gc)
    im = Image.fromarray(np.clip(diff, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(2))
    return np.asarray(im, dtype=np.float64)


def containment(base: Any, cand: Any, region: Optional[dict] = None) -> float:
    """Share of blurred absolute-difference mass inside the region. No region → 1.0; no change → 1.0."""
    if region is None:
        return 1.0
    d = _blurred_absdiff(base, cand)
    total = d.sum()
    if total < 1e-6:
        return 1.0
    inside = _region_mask(d.shape, region)
    return float(np.clip(d[inside].sum() / total, 0.0, 1.0))


def fidelity(base: Any, cand: Any, region: Optional[dict] = None) -> dict:
    """spec §6.4: fidelity = 0.5 * clamp((embed_cos − 0.6) / 0.4) + 0.5 * ssim_out; plus the parts."""
    b, c = load_image(base), load_image(cand)
    cos = embed_cos(image_embed(b), image_embed(c))
    s = ssim_out(b, c, region)
    cont = containment(b, c, region)
    f = 0.5 * float(np.clip((cos - 0.6) / 0.4, 0.0, 1.0)) + 0.5 * s
    return {"fidelity": float(f), "embed_cos": cos, "ssim_out": s, "containment": cont, "embed_backend": image_embed_backend()}


def diff_heatmap(base: Any, cand: Any) -> bytes:
    """PNG the size of `base`: a faded copy with the blurred absolute difference painted warm (yellow→red)."""
    b = load_image(base)
    c = load_image(cand)
    if c.size != b.size:
        c = c.resize(b.size, Image.BILINEAR)
    gb = np.asarray(b.convert("L"), dtype=np.float64)
    gc = np.asarray(c.convert("L"), dtype=np.float64)
    diff = np.abs(gb - gc)
    blur = np.asarray(Image.fromarray(np.clip(diff, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(3)), dtype=np.float64)
    peak = max(blur.max(), 1.0)
    t = np.clip(blur / peak, 0.0, 1.0)
    faded = (np.asarray(b, dtype=np.float64) * 0.45 + 255.0 * 0.55)
    warm = np.stack([np.full_like(t, 220.0), 200.0 - 170.0 * t, 40.0 * (1.0 - t)], axis=-1)  # yellow → red
    alpha = (t ** 0.7)[..., None] * 0.85
    out = faded * (1.0 - alpha) + warm * alpha
    buf = io.BytesIO()
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB").save(buf, format="PNG")
    return buf.getvalue()

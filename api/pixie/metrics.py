"""Distances between an intent and a reading, and the Maker score (spec §6.2–6.3).

d_axes  = ||a_i - a_r||_2 / (6*sqrt(8))           0..1
d_embed = (1 - cos(e_i, e_r)) / 2                  0..1, only when both texts exist
d_total = w_axes*d_axes + w_embed*d_embed          if d_embed exists, else d_axes
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

import numpy as np

from .axes import AXIS_MAX, N_AXES

RADIUS = 0.30
W_AXES = 0.6
W_EMBED = 0.4
MAX_AXES_DIST = 2 * AXIS_MAX * math.sqrt(N_AXES)  # 6*sqrt(8): opposite corners of [-3,3]^8

DEFAULT_CFG = {"w_axes": W_AXES, "w_embed": W_EMBED, "radius": RADIUS}


def _cfg(cfg: Optional[dict]) -> dict:
    out = dict(DEFAULT_CFG)
    if cfg:
        out.update({k: v for k, v in cfg.items() if k in out and v is not None})
    return out


def d_axes(a: Sequence[float], b: Sequence[float]) -> float:
    a = np.asarray(a, dtype=float).reshape(-1)
    b = np.asarray(b, dtype=float).reshape(-1)
    return float(min(1.0, np.linalg.norm(a - b) / MAX_AXES_DIST))


def d_embed(e1: Sequence[float], e2: Sequence[float]) -> float:
    e1 = np.asarray(e1, dtype=float).reshape(-1)
    e2 = np.asarray(e2, dtype=float).reshape(-1)
    n1, n2 = np.linalg.norm(e1), np.linalg.norm(e2)
    if n1 == 0 or n2 == 0:
        return 0.5  # undefined direction: maximal uncertainty, not maximal distance
    cos = float(np.dot(e1, e2) / (n1 * n2))
    cos = max(-1.0, min(1.0, cos))
    return (1.0 - cos) / 2.0


def d_total(
    a_i: Sequence[float],
    a_r: Sequence[float],
    e_i: Optional[Sequence[float]] = None,
    e_r: Optional[Sequence[float]] = None,
    cfg: Optional[dict] = None,
) -> dict:
    c = _cfg(cfg)
    da = d_axes(a_i, a_r)
    de: Optional[float] = None
    if e_i is not None and e_r is not None:
        de = d_embed(e_i, e_r)
        dt = c["w_axes"] * da + c["w_embed"] * de
    else:
        dt = da
    return {
        "d_axes": da,
        "d_embed": de,
        "d_total": float(dt),
        "inside_radius": bool(dt <= c["radius"]),
    }


def maker_score(d_totals: Sequence[float], cfg: Optional[dict] = None) -> dict:
    """Dixit-style score computed from reports. f = share of readers inside the radius.

    N >= 3 readers required. 0.25 <= f <= 0.75 → 3, f > 0.75 → 1, f < 0.25 → 0."""
    c = _cfg(cfg)
    ds = [float(d) for d in d_totals]
    n = len(ds)
    if n < 3:
        return {"points": None, "f": (sum(d <= c["radius"] for d in ds) / n if n else None), "n": n, "needs": 3}
    f = sum(d <= c["radius"] for d in ds) / n
    if 0.25 <= f <= 0.75:
        pts = 3
    elif f > 0.75:
        pts = 1
    else:
        pts = 0
    return {"points": pts, "f": float(f), "n": n, "needs": 3}


def fidelity(d_totals: Sequence[float]) -> Optional[float]:
    """Transmission fidelity of an intent = 1 - mean(d_total). None when there are no readings."""
    ds = [float(d) for d in d_totals]
    if not ds:
        return None
    return float(1.0 - sum(ds) / len(ds))


# ----------------------------------------------------------------------------- v4: relay metrics (§6.2–6.3)
LANDING_F = 0.80
LANDING_MIN_READERS = 2
BET_THRESHOLD = 0.5


def gaps(intent_axes: Sequence[float], readings_axes: Sequence[Sequence[float]]) -> np.ndarray:
    """g_k = intent_k − mean(reading_k). Zeros when there are no readings."""
    a = np.asarray(intent_axes, dtype=float).reshape(N_AXES)
    R = np.asarray(readings_axes, dtype=float).reshape(-1, N_AXES)
    if R.shape[0] == 0:
        return np.zeros(N_AXES)
    return a - R.mean(0)


def paired_shift(prev: dict, cur: dict) -> tuple[Optional[np.ndarray], int]:
    """Mean per-axis shift over readers present in both maps {reader_id: axes}. (None, 0) without pairs."""
    ids = [k for k in cur if k in prev]
    if not ids:
        return None, 0
    P = np.asarray([prev[k] for k in ids], dtype=float).reshape(-1, N_AXES)
    C = np.asarray([cur[k] for k in ids], dtype=float).reshape(-1, N_AXES)
    return (C - P).mean(0), len(ids)


def bet_hit(delta_k: float, gap_before_k: float, threshold: float = BET_THRESHOLD) -> bool:
    """The Editor's bet lands when the paired shift on the bet axis goes the way of the gap and is ≥ threshold."""
    if gap_before_k == 0 or delta_k == 0:
        return False
    return bool(np.sign(delta_k) == np.sign(gap_before_k) and abs(delta_k) >= threshold)


def landed(fidelity_value: Optional[float], n_human: int) -> bool:
    """A version lands when F ≥ LANDING_F with at least LANDING_MIN_READERS human readings."""
    if fidelity_value is None:
        return False
    return bool(n_human >= LANDING_MIN_READERS and fidelity_value >= LANDING_F)

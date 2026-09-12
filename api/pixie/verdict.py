"""Polysemy verdict (spec §6.4) — AXES ONLY, null-calibrated silhouette.

x        = axes / 3                                         8-d in [-1, 1]
V        = mean pairwise euclidean distance / (2*sqrt(8))    raw variance, 0..1
S        = max over k in {2,3} of silhouette(KMeans(k, n_init=10).fit(x))
null     = n_null draws of N isotropic-Gaussian points, rescaled to the same V
S_null95 = 95th percentile of the null's max-silhouette

legible     V < v_lo
polysemous  V >= v_lo and S >  S_null95
noisy       V >= v_lo and S <= S_null95

Silhouette is scale-invariant, so the null depends only on N: it is tabulated once per N
(pixie/null_table.json, built by scripts/build_null_table.py) and cached in-process.
"""
from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from typing import Optional, Sequence

import numpy as np

from .axes import AXIS_MAX, N_AXES

V_LO = 0.30
N_NEEDED = 8
K_VALUES = (2, 3)
_TABLE_PATH = os.path.join(os.path.dirname(__file__), "null_table.json")
_V_SCALE = 2.0 * math.sqrt(N_AXES)


# ----------------------------------------------------------------------------- basics

def pairwise_distances(x: np.ndarray) -> np.ndarray:
    """(n, d) → (n, n) euclidean distance matrix."""
    diff = x[:, None, :] - x[None, :, :]
    return np.sqrt((diff * diff).sum(-1))


def raw_variance(x: np.ndarray) -> float:
    """V = mean pairwise euclidean distance / (2*sqrt(8)) for x in [-1,1]^8."""
    n = len(x)
    if n < 2:
        return 0.0
    D = pairwise_distances(x)
    iu = np.triu_indices(n, 1)
    return float(D[iu].mean() / _V_SCALE)


def silhouette_np(D: np.ndarray, labels: np.ndarray) -> float:
    """Mean silhouette from a distance matrix (same convention as sklearn: singletons score 0)."""
    s = _batched_silhouette(D[None, :, :], np.asarray(labels)[None, :], int(np.max(labels)) + 1)
    return float(s[0])


# ----------------------------------------------------------------------------- batched k-means (null only)

def _kmeanspp_init(X: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    B, n, d = X.shape
    centers = np.empty((B, k, d))
    ar = np.arange(B)
    idx0 = rng.integers(0, n, B)
    centers[:, 0] = X[ar, idx0]
    d2 = ((X - centers[:, 0:1]) ** 2).sum(-1)
    for j in range(1, k):
        tot = d2.sum(1, keepdims=True)
        probs = np.where(tot > 1e-12, d2 / np.maximum(tot, 1e-12), 1.0 / n)
        cum = probs.cumsum(1)
        r = rng.random((B, 1))
        idx = np.clip((cum < r).sum(1), 0, n - 1)
        centers[:, j] = X[ar, idx]
        d2 = np.minimum(d2, ((X - centers[:, j : j + 1]) ** 2).sum(-1))
    return centers


def _batched_kmeans(X: np.ndarray, k: int, rng: np.random.Generator, n_init: int = 10, max_iter: int = 50) -> np.ndarray:
    """X: (b, n, d). Runs n_init k-means++ starts per draw, returns best-inertia labels (b, n)."""
    b, n, d = X.shape
    Xr = np.repeat(X, n_init, axis=0)  # (B, n, d), B = b*n_init
    B = Xr.shape[0]
    centers = _kmeanspp_init(Xr, k, rng)
    ks = np.arange(k)
    labels = None
    for _ in range(max_iter):
        dist = ((Xr[:, :, None, :] - centers[:, None, :, :]) ** 2).sum(-1)  # (B, n, k)
        labels = dist.argmin(-1)
        onehot = (labels[..., None] == ks).astype(float)  # (B, n, k)
        counts = onehot.sum(1)  # (B, k)
        sums = np.einsum("bnk,bnd->bkd", onehot, Xr)
        new_centers = sums / np.maximum(counts, 1)[..., None]
        empty = counts == 0
        new_centers[empty] = centers[empty]
        if np.allclose(new_centers, centers, atol=1e-9, rtol=0):
            centers = new_centers
            break
        centers = new_centers
    dist = ((Xr[:, :, None, :] - centers[:, None, :, :]) ** 2).sum(-1)
    labels = dist.argmin(-1)
    inertia = dist.min(-1).sum(1).reshape(b, n_init)
    best = inertia.argmin(1)
    return labels.reshape(b, n_init, n)[np.arange(b), best]


def _batched_silhouette(D: np.ndarray, labels: np.ndarray, k: int) -> np.ndarray:
    """D: (b, n, n) distances, labels: (b, n) in 0..k-1 → mean silhouette per draw (b,)."""
    b, n, _ = D.shape
    ks = np.arange(k)
    onehot = (labels[..., None] == ks).astype(float)  # (b, n, k)
    counts = onehot.sum(1)  # (b, k)
    sums = np.einsum("bij,bjk->bik", D, onehot)  # (b, n, k)
    own = labels[..., None]
    cnt_own = np.take_along_axis(counts[:, None, :], own, 2)[..., 0]  # (b, n)
    sum_own = np.take_along_axis(sums, own, 2)[..., 0]
    a = sum_own / np.maximum(cnt_own - 1, 1)
    means = sums / np.maximum(counts, 1)[:, None, :]
    means = np.where(counts[:, None, :] == 0, np.inf, means)
    np.put_along_axis(means, own, np.inf, 2)
    bb = means.min(2)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = (bb - a) / np.maximum(np.maximum(a, bb), 1e-12)
    s = np.where(np.isfinite(s), s, 0.0)
    s = np.where(cnt_own == 1, 0.0, s)
    nonempty = (counts > 0).sum(1)  # draws with < 2 non-empty clusters have no structure
    out = s.mean(1)
    out = np.where(nonempty < 2, 0.0, out)
    return out


def null_max_silhouettes(
    n: int, v_target: float = 1.0, n_null: int = 200, seed: int = 0, k_values: Sequence[int] = K_VALUES
) -> np.ndarray:
    """n_null draws of n isotropic-Gaussian points in 8-d, each rescaled to raw variance v_target,
    clustered with k in k_values; returns the max silhouette per draw, shape (n_null,)."""
    rng = np.random.default_rng(np.random.SeedSequence([int(seed), int(n)]))
    Z = rng.standard_normal((n_null, n, N_AXES))
    D = np.sqrt(((Z[:, :, None, :] - Z[:, None, :, :]) ** 2).sum(-1))  # (n_null, n, n)
    V = D.sum((1, 2)) / (n * (n - 1)) / _V_SCALE
    scale = (v_target / np.maximum(V, 1e-12))[:, None, None]
    Z = Z * scale  # rescale to the same V (silhouette is scale-invariant; done literally per spec)
    D = D * scale
    best = np.full(n_null, -1.0)
    for k in k_values:
        if k >= n:
            continue
        labels = _batched_kmeans(Z, k, rng)
        best = np.maximum(best, _batched_silhouette(D, labels, k))
    return best


@lru_cache(maxsize=1)
def _load_table() -> dict:
    if os.path.exists(_TABLE_PATH):
        try:
            with open(_TABLE_PATH) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


@lru_cache(maxsize=4096)
def null_s95(n: int, n_null: int = 200, seed: int = 0) -> float:
    """95th percentile of the null max-silhouette for N = n points (table lookup, else computed)."""
    table = _load_table()
    if table and table.get("n_null") == n_null and table.get("seed") == seed:
        v = table.get("s95", {}).get(str(int(n)))
        if v is not None:
            return float(v)
    best = null_max_silhouettes(int(n), 1.0, n_null, seed)
    return float(np.percentile(best, 95))


# ----------------------------------------------------------------------------- the verdict

def _real_clustering(x: np.ndarray, seed: int) -> tuple[int, float, np.ndarray]:
    """sklearn KMeans(k, n_init=10) for k in {2,3}; returns (best_k, best_S, labels). S=0, k=1 if degenerate."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    n = len(x)
    n_unique = len(np.unique(x, axis=0))
    best_k, best_s, best_labels = 1, None, np.zeros(n, dtype=int)
    for k in K_VALUES:
        if n <= k or n_unique <= k:
            continue
        km = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(x)
        labels = km.labels_.astype(int)
        if len(np.unique(labels)) < 2:
            continue
        s = float(silhouette_score(x, labels))
        if best_s is None or s > best_s:
            best_k, best_s, best_labels = k, s, labels
    return best_k, (best_s if best_s is not None else 0.0), best_labels


def polysemy_verdict(
    axes: Sequence[Sequence[float]],
    v_lo: float = V_LO,
    n_null: int = 200,
    seed: int = 0,
    cfg: Optional[dict] = None,
) -> dict:
    A = np.asarray(axes, dtype=float).reshape(-1, N_AXES)
    n = int(len(A))
    if cfg and cfg.get("v_lo") is not None:
        v_lo = float(cfg["v_lo"])
    if n < N_NEEDED:
        return {"verdict": "collecting", "n": n, "needed": N_NEEDED}

    x = A / AXIS_MAX
    V = raw_variance(x)
    if V <= 1e-12:
        k, S, labels = 1, 0.0, np.zeros(n, dtype=int)
    else:
        k, S, labels = _real_clustering(x, seed)
    S_null95 = null_s95(n, n_null, seed)

    if V < v_lo:
        verdict = "legible"
        k, labels = 1, np.zeros(n, dtype=int)
    elif S > S_null95:
        verdict = "polysemous"
    else:
        verdict = "noisy"

    P = float(V * max(S - S_null95, 0.0))
    noise = float(V - P)
    clusters = []
    for c in range(k):
        idx = np.where(labels == c)[0]
        if len(idx) == 0:
            continue
        clusters.append({
            "centroid": [float(v) for v in A[idx].mean(0)],
            "n": int(len(idx)),
            "member_idx": [int(i) for i in idx],
        })
    return {
        "verdict": verdict,
        "n": n,
        "needed": N_NEEDED,
        "V": float(V),
        "S": float(S),
        "S_null95": float(S_null95),
        "k": int(k),
        "P": P,
        "noise": noise,
        "v_lo": float(v_lo),
        "labels": [int(l) for l in labels],
        "clusters": clusters,
    }

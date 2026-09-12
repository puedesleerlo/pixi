"""Reveal geometry (spec §6.9): PCA to 2 components, fitted ONCE on seed intents + readings and frozen."""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from .axes import N_AXES


class FrozenPCA:
    def __init__(self) -> None:
        self.mean: Optional[np.ndarray] = None
        self.components: Optional[np.ndarray] = None  # (2, 8)
        self.explained: Optional[np.ndarray] = None  # (2,) variance ratio
        self.n_fit: int = 0

    def fit(self, points: Sequence[Sequence[float]]) -> "FrozenPCA":
        P = np.asarray(points, dtype=float).reshape(-1, N_AXES)
        if len(P) == 0:
            raise ValueError("FrozenPCA.fit needs at least one point")
        self.mean = P.mean(0)
        Xc = P - self.mean
        if len(P) == 1:
            comps = np.zeros((2, N_AXES)); comps[0, 0] = 1.0; comps[1, 1] = 1.0
            self.components, self.explained, self.n_fit = comps, np.zeros(2), 1
            return self
        _, s, vt = np.linalg.svd(Xc, full_matrices=False)
        comps = np.zeros((2, N_AXES))
        take = min(2, vt.shape[0])
        comps[:take] = vt[:take]
        if take < 2:  # rank-1 data: pick any orthogonal axis
            comps[1] = np.eye(N_AXES)[np.argmin(np.abs(comps[0]))]
        # deterministic sign: largest-|loading| positive
        for i in range(2):
            j = int(np.argmax(np.abs(comps[i])))
            if comps[i, j] < 0:
                comps[i] = -comps[i]
        var = s ** 2
        tot = var.sum() if var.sum() > 0 else 1.0
        expl = np.zeros(2); expl[:take] = var[:take] / tot
        self.components, self.explained, self.n_fit = comps, expl, int(len(P))
        return self

    def transform(self, points: Sequence[Sequence[float]]) -> np.ndarray:
        if self.components is None or self.mean is None:
            raise ValueError("FrozenPCA is not fitted")
        P = np.asarray(points, dtype=float).reshape(-1, N_AXES)
        return (P - self.mean) @ self.components.T  # (M, 2)

    def to_dict(self) -> dict:
        return {
            "mean": self.mean.tolist() if self.mean is not None else None,
            "components": self.components.tolist() if self.components is not None else None,
            "explained": self.explained.tolist() if self.explained is not None else None,
            "n_fit": self.n_fit,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FrozenPCA":
        p = cls()
        if d and d.get("mean") is not None and d.get("components") is not None:
            p.mean = np.asarray(d["mean"], dtype=float)
            p.components = np.asarray(d["components"], dtype=float).reshape(2, N_AXES)
            p.explained = np.asarray(d.get("explained") or [0, 0], dtype=float)
            p.n_fit = int(d.get("n_fit") or 0)
        return p

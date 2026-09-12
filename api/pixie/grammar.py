"""The grammar: ridge regression of reading axes on visual salience (spec §6.5).

X[i, j] = visual_salience of element j in the card read at event i
Y[i, :] = axes of reading i
W       = ridge(X, Y, alpha=1.0, fit_intercept=True)        # 8 coefficients per element
Bootstrap over readings for 95% CIs.  historical_support(j) = cosine(W[j], prior_j).
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from .axes import N_AXES


def _ridge(X: np.ndarray, Y: np.ndarray, alpha: float, w: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Closed-form ridge with an unpenalised intercept (identical to sklearn Ridge(fit_intercept=True)).
    Optional per-row weights `w` (weighted least squares: rows scaled by sqrt(w), weighted centering).
    Returns (coef (E, 8), intercept (8,))."""
    if w is None:
        xm = X.mean(0)
        ym = Y.mean(0)
        Xc = X - xm
        Yc = Y - ym
    else:
        w = np.asarray(w, dtype=float)
        tot = w.sum()
        xm = (w[:, None] * X).sum(0) / tot
        ym = (w[:, None] * Y).sum(0) / tot
        sw = np.sqrt(w)[:, None]
        Xc = (X - xm) * sw
        Yc = (Y - ym) * sw
    E = X.shape[1]
    A = Xc.T @ Xc + alpha * np.eye(E)
    W = np.linalg.solve(A, Xc.T @ Yc)  # (E, 8)
    b = ym - xm @ W
    return W, b


def fit_grammar(
    X: Sequence[Sequence[float]],
    Y: Sequence[Sequence[float]],
    alpha: float = 1.0,
    n_boot: int = 200,
    seed: int = 0,
    sample_weight: Sequence[float] | None = None,
) -> dict:
    """`sample_weight` (optional, per row): e.g. down-weight synthetic seed readings so that real
    readings dominate as they accumulate. The bootstrap resamples rows and keeps their weights."""
    X = np.asarray(X, dtype=float)
    Y = np.asarray(Y, dtype=float)
    if X.ndim != 2:
        X = X.reshape(-1, X.shape[-1] if X.ndim else 0)
    N, E = X.shape
    Y = Y.reshape(N, N_AXES) if N else Y.reshape(0, N_AXES)
    zeros = np.zeros((E, N_AXES))
    if N == 0:
        return {"coef": zeros.tolist(), "ci_low": zeros.tolist(), "ci_high": zeros.tolist(),
                "intercept": [0.0] * N_AXES, "n": 0, "alpha": alpha, "n_boot": 0}
    w = None if sample_weight is None else np.asarray(sample_weight, dtype=float).reshape(N)
    W, b = _ridge(X, Y, alpha, w)
    if n_boot > 0 and N >= 2:
        rng = np.random.default_rng(seed)
        boots = np.empty((n_boot, E, N_AXES))
        for k in range(n_boot):
            idx = rng.integers(0, N, N)
            boots[k], _ = _ridge(X[idx], Y[idx], alpha, None if w is None else w[idx])
        ci_low = np.percentile(boots, 2.5, axis=0)
        ci_high = np.percentile(boots, 97.5, axis=0)
    else:
        ci_low, ci_high = W.copy(), W.copy()
    return {
        "coef": W.tolist(),
        "ci_low": ci_low.tolist(),
        "ci_high": ci_high.tolist(),
        "intercept": b.tolist(),
        "n": int(N),
        "alpha": float(alpha),
        "n_boot": int(n_boot if N >= 2 else 0),
    }


def historical_support(coef_row: Sequence[float], prior: Sequence[float]) -> float:
    """cosine(W[j], historical_prior_j); 0.0 if either vector is zero. Negative = drifting against tradition."""
    a = np.asarray(coef_row, dtype=float).reshape(-1)
    b = np.asarray(prior, dtype=float).reshape(-1)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))


def grammar_correlation(W: Sequence[Sequence[float]], W_star: Sequence[Sequence[float]]) -> float:
    """corr(vec(W), vec(W*)) — the estimator test statistic (spec §6.7)."""
    a = np.asarray(W, dtype=float).reshape(-1)
    b = np.asarray(W_star, dtype=float).reshape(-1)
    if a.std() < 1e-12 or b.std() < 1e-12:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])

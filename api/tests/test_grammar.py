import numpy as np
from sklearn.linear_model import Ridge
from pixie.grammar import fit_grammar, historical_support, grammar_correlation, _ridge


def test_closed_form_matches_sklearn():
    rng = np.random.default_rng(0)
    X = rng.random((50, 6)); Y = rng.normal(size=(50, 8))
    W, b = _ridge(X, Y, 1.0)
    m = Ridge(alpha=1.0, fit_intercept=True).fit(X, Y)
    assert np.allclose(W, m.coef_.T, atol=1e-8) and np.allclose(b, m.intercept_, atol=1e-8)


def test_recovers_planted_grammar():
    rng = np.random.default_rng(1)
    C, E, N = 60, 10, 300
    Xc = np.where(rng.random((C, E)) < 0.4, rng.random((C, E)), 0.0)
    W_true = rng.uniform(-2.5, 2.5, (E, 8))
    idx = rng.integers(0, C, N)
    X = Xc[idx]; Y = X @ W_true + rng.normal(0, 0.8, (N, 8))
    g = fit_grammar(X, Y, alpha=1.0, n_boot=100, seed=0)
    assert grammar_correlation(g["coef"], W_true) > 0.9
    lo, hi, W = np.array(g["ci_low"]), np.array(g["ci_high"]), np.array(g["coef"])
    assert np.all(lo <= W + 1e-9) and np.all(W <= hi + 1e-9)
    covered = np.mean((lo <= W_true) & (W_true <= hi))
    assert covered > 0.75
    assert g["n"] == N and len(g["intercept"]) == 8


def test_underdetermined_and_empty():
    rng = np.random.default_rng(2)
    X = rng.random((5, 20)); Y = rng.normal(size=(5, 8))
    g = fit_grammar(X, Y, n_boot=20)
    assert np.isfinite(g["coef"]).all() and len(g["coef"]) == 20
    g0 = fit_grammar(np.zeros((0, 4)), np.zeros((0, 8)))
    assert g0["n"] == 0 and len(g0["coef"]) == 4


def test_historical_support():
    assert historical_support([1, 0, 0, 0, 0, 0, 0, 0], [2, 0, 0, 0, 0, 0, 0, 0]) == 1.0
    assert historical_support([1, 0, 0, 0, 0, 0, 0, 0], [-1, 0, 0, 0, 0, 0, 0, 0]) == -1.0
    assert historical_support([0]*8, [1]*8) == 0.0

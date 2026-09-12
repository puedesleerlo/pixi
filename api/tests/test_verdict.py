import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from pixie.verdict import polysemy_verdict, raw_variance, silhouette_np, pairwise_distances, null_s95


def _bimodal(n=16, seed=0):
    rng = np.random.default_rng(seed)
    d = np.zeros(8); d[:3] = 1/np.sqrt(3)
    pts = [ (4.0*d if i % 2 == 0 else -4.0*d) + rng.normal(0, 0.3, 8) for i in range(n)]
    return np.clip(np.array(pts), -3, 3)


def test_collecting_below_eight():
    r = polysemy_verdict(np.zeros((7, 8)))
    assert r["verdict"] == "collecting" and r["n"] == 7 and r["needed"] == 8


def test_identical_points_are_legible():
    r = polysemy_verdict(np.ones((10, 8)) * 2)
    assert r["verdict"] == "legible" and r["V"] == 0.0 and r["k"] == 1


def test_bimodal_is_polysemous():
    for seed in range(3):
        r = polysemy_verdict(_bimodal(16, seed), v_lo=0.2, seed=seed)
        assert r["verdict"] == "polysemous", r
        assert r["k"] == 2 and r["S"] > r["S_null95"] and r["P"] > 0
        assert sorted(c["n"] for c in r["clusters"]) == [8, 8]
        assert len(r["labels"]) == 16


def test_isotropic_is_rarely_polysemous():
    rng = np.random.default_rng(123)
    hits = 0
    for t in range(40):
        pts = np.clip(rng.normal(0, 1.4, (16, 8)), -3, 3)
        r = polysemy_verdict(pts, v_lo=0.05, seed=t)
        assert r["verdict"] in ("noisy", "polysemous")
        hits += r["verdict"] == "polysemous"
    assert hits <= 8  # expected 5% false positives → ~2 of 40


def test_low_variance_is_legible():
    rng = np.random.default_rng(7)
    pts = np.clip(1.0 + rng.normal(0, 0.15, (12, 8)), -3, 3)
    r = polysemy_verdict(pts, v_lo=0.3)
    assert r["verdict"] == "legible" and r["V"] < 0.3


def test_silhouette_matches_sklearn():
    rng = np.random.default_rng(3)
    x = rng.normal(size=(20, 8))
    lab = KMeans(3, n_init=10, random_state=0).fit(x).labels_
    assert abs(silhouette_np(pairwise_distances(x), lab) - silhouette_score(x, lab)) < 1e-9


def test_null_table_monotone_and_cached():
    a, b, c = null_s95(8), null_s95(20), null_s95(80)
    assert 0 < c < b < a < 1
    assert null_s95(12) == null_s95(12)


def test_raw_variance_range():
    assert raw_variance(np.array([[-1]*8, [1]*8])) == 1.0

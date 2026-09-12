import numpy as np
from pixie.geometry import FrozenPCA


def test_fit_transform_roundtrip():
    rng = np.random.default_rng(0)
    P = rng.normal(size=(100, 8)) @ np.diag([3, 2, 1, .5, .5, .2, .2, .1])
    pca = FrozenPCA().fit(P)
    xy = pca.transform(P)
    assert xy.shape == (100, 2)
    assert pca.explained[0] >= pca.explained[1] > 0
    again = FrozenPCA.from_dict(pca.to_dict())
    assert np.allclose(again.transform(P), xy)
    assert np.allclose(FrozenPCA().fit(P).transform(P), xy)  # deterministic sign
    assert pca.transform([[0]*8]).shape == (1, 2)


def test_degenerate_fits():
    p1 = FrozenPCA().fit([[1]*8])
    assert p1.transform([[1]*8]).shape == (1, 2)
    line = np.outer(np.arange(5), np.ones(8))
    p2 = FrozenPCA().fit(line)
    assert np.isfinite(p2.transform(line)).all()

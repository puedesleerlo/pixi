import os
import numpy as np
import pixie.embed as em


def test_hash_backend():
    os.environ["PIXIE_EMBED"] = "hash"
    em._backend = None
    assert em.backend_name() == "hash"
    v = em.embed(["a star over falling water", "a star over falling water", "a tower struck", ""])
    assert v.shape == (4, 384)
    assert np.allclose(v[0], v[1]) and not np.allclose(v[0], v[2])
    assert abs(np.linalg.norm(v[0]) - 1) < 1e-9 and np.linalg.norm(v[3]) == 0
    assert em.embed([]).shape == (0, 384)

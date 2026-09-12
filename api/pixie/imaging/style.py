"""Style coherence: a centroid embedding of the style references + landed cards, and a per-image score."""
from __future__ import annotations

from typing import Any, Iterable, Optional

import numpy as np

from .fidelity import EMBED_DIM, embed_cos, image_embed


def style_centroid(images: Iterable[Any]) -> Optional[np.ndarray]:
    """Mean of the images' embeddings, L2-normalised; None when there are no images."""
    vecs = [image_embed(im) for im in images]
    if not vecs:
        return None
    c = np.mean(np.stack(vecs), axis=0)
    n = np.linalg.norm(c)
    return (c / n).astype(np.float32) if n > 1e-12 else np.zeros(EMBED_DIM, dtype=np.float32)


def style_score(img: Any, centroid: Optional[Any]) -> Optional[float]:
    """Cosine to the centroid, clipped to 0..1; None when the deck has no centroid yet."""
    if centroid is None:
        return None
    c = np.asarray(centroid, dtype=np.float32).ravel()
    if c.size == 0 or np.linalg.norm(c) < 1e-12:
        return None
    v = image_embed(img)
    if c.size != v.size:  # different backend widths: compare on the shared prefix
        k = min(c.size, v.size)
        c, v = c[:k], v[:k]
    return float(np.clip(embed_cos(v, c), 0.0, 1.0))

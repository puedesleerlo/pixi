"""Text embeddings, local only (spec §4): sentence-transformers/all-MiniLM-L6-v2 (384-d).

Fallback when the model is not importable (or PIXIE_EMBED=hash): a deterministic hashed
bag-of-words into 384 buckets, L2-normalised. Never Gemini (different dimensionality).
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Optional, Sequence

import numpy as np

DIM = 384
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_backend: Optional[str] = None
_model = None
_TOKEN = re.compile(r"[a-z0-9']+")


def _load() -> None:
    global _backend, _model
    if _backend is not None:
        return
    if os.environ.get("PIXIE_EMBED", "").strip().lower() == "hash":
        _backend = "hash"
        return
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        try:
            _model = SentenceTransformer(MODEL_NAME, local_files_only=True)
        except Exception:
            _model = SentenceTransformer(MODEL_NAME)
        _backend = "minilm"
    except Exception:
        _model = None
        _backend = "hash"


def backend_name() -> str:
    _load()
    return _backend or "hash"


def warmup() -> str:
    """Load the model eagerly (call at server startup so the first round is not slow)."""
    _load()
    if _backend == "minilm":
        embed(["warmup"])
    return backend_name()


def _hash_embed(text: str) -> np.ndarray:
    v = np.zeros(DIM, dtype=float)
    for tok in _TOKEN.findall((text or "").lower()):
        h = hashlib.md5(tok.encode("utf-8")).digest()
        bucket = int.from_bytes(h[:4], "little") % DIM
        sign = 1.0 if (h[4] & 1) else -1.0
        v[bucket] += sign
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def embed(texts: Sequence[str]) -> np.ndarray:
    """(n, 384) float array; empty strings → zero vectors."""
    _load()
    texts = [t if isinstance(t, str) else "" for t in texts]
    if not texts:
        return np.zeros((0, DIM), dtype=float)
    if _backend == "minilm" and _model is not None:
        out = np.zeros((len(texts), DIM), dtype=float)
        idx = [i for i, t in enumerate(texts) if t.strip()]
        if idx:
            vecs = _model.encode([texts[i] for i in idx], normalize_embeddings=True, show_progress_bar=False)
            out[idx] = np.asarray(vecs, dtype=float)
        return out
    return np.stack([_hash_embed(t) for t in texts])

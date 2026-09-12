"""The eight bipolar scales (Osgood semantic differential). Negative = first pole, positive = second."""
from __future__ import annotations

from typing import Sequence

import numpy as np

AXES: list[tuple[str, str]] = [
    ("active", "passive"),
    ("beginning", "ending"),
    ("giving", "withholding"),
    ("inward", "outward"),
    ("gain", "loss"),
    ("willing", "compelled"),
    ("certain", "uncertain"),
    ("singular", "collective"),
]
N_AXES = 8
AXIS_MAX = 3.0


def pole_word(i: int, value: float) -> str:
    """The pole word for axis i given the sign of value (0 → first pole)."""
    return AXES[i][1] if value > 0 else AXES[i][0]


def axes_to_words(vec: Sequence[float], k: int = 3) -> str:
    """Render the k largest-|v| axes as pole words, strongest first, joined with ' · '.

    Axes with value exactly 0 are skipped (they carry no direction)."""
    v = np.asarray(vec, dtype=float).reshape(-1)
    order = np.argsort(-np.abs(v), kind="stable")[:k]
    words = [pole_word(int(i), float(v[i])) for i in order if v[i] != 0]
    return " · ".join(words)

"""Edit-effect estimator (spec v4 §6.5).

Each one-element edit with paired readers observes ±salience_s · W[e] directly:
    add    → shift / s                (s = the added element's slot salience)
    remove → −shift / s
    swap   → shift / s to the incoming element, −shift / s to the outgoing one
             (confounded by construction: shift/s = W[in] − W[out]; pass the pooled `coef` to
              correct each side with the other's pooled coefficient)
    move   → shift / (s_new − s_old)  (skipped when the salience does not change)
The result is averaged per element and reported beside the pooled ridge coefficient.
"""
from __future__ import annotations

from typing import Mapping, Optional, Sequence

import numpy as np

from .axes import N_AXES
from .metrics import paired_shift
from .slots import SLOTS


def _reader_map(readings: Sequence[Mapping]) -> dict[str, list]:
    """{reader_id: axes} for one version; a reader's last reading wins."""
    out: dict[str, list] = {}
    for r in readings:
        out[r["reader_id"]] = r["axes"]
    return out


def _slot_of(version: Mapping, eid: str) -> Optional[str]:
    for it in version.get("elements", []):
        if it["element_id"] == eid:
            return it["slot"]
    return None


def edit_effects(
    versions: Sequence[Mapping],
    readings: Sequence[Mapping],
    coef: Optional[Mapping[str, Sequence[float]]] = None,
) -> dict[str, dict]:
    """→ {element_id: {"n_edits", "mean_effect": [8], "n_pairs"}} from paired readings across edits.

    `coef` (optional): pooled coefficients {element_id: [8]} used only to de-confound swaps."""
    by_version: dict[str, list] = {}
    for r in readings:
        by_version.setdefault(r["version_id"], []).append(r)
    parent_of: dict[str, Mapping] = {}
    by_card_v: dict[tuple, Mapping] = {(v["card_id"], int(v["v"])): v for v in versions}
    acc: dict[str, list[np.ndarray]] = {}
    pairs: dict[str, int] = {}

    def push(eid: str, eff: np.ndarray, n: int) -> None:
        acc.setdefault(eid, []).append(np.asarray(eff, dtype=float).reshape(N_AXES))
        pairs[eid] = pairs.get(eid, 0) + n

    for v in versions:
        edit = v.get("edit")
        if not edit or int(v.get("v", 0)) < 1:
            continue
        parent = by_card_v.get((v["card_id"], int(v["v"]) - 1))
        if parent is None:
            continue
        delta, n = paired_shift(_reader_map(by_version.get(parent["id"], [])), _reader_map(by_version.get(v["id"], [])))
        if delta is None:
            continue
        kind = edit.get("type")
        eid = edit.get("element_id")
        if kind == "add":
            slot = _slot_of(v, eid)
            if slot:
                push(eid, delta / SLOTS[slot], n)
        elif kind == "remove":
            slot = _slot_of(parent, eid)
            if slot:
                push(eid, -delta / SLOTS[slot], n)
        elif kind == "swap":
            to = edit.get("to_element_id")
            slot = _slot_of(parent, eid) or _slot_of(v, to)
            if slot and to:
                s = SLOTS[slot]
                if coef is not None and eid in coef and to in coef:
                    push(to, delta / s + np.asarray(coef[eid], dtype=float), n)
                    push(eid, np.asarray(coef[to], dtype=float) - delta / s, n)
                else:
                    push(to, delta / s, n)
                    push(eid, -delta / s, n)
        elif kind == "move":
            s_old = SLOTS.get(_slot_of(parent, eid) or "", None)
            s_new = SLOTS.get(_slot_of(v, eid) or "", None)
            if s_old is not None and s_new is not None and abs(s_new - s_old) > 1e-9:
                push(eid, delta / (s_new - s_old), n)

    return {
        eid: {"n_edits": len(effs), "mean_effect": [float(x) for x in np.mean(effs, axis=0)], "n_pairs": pairs[eid]}
        for eid, effs in acc.items()
    }

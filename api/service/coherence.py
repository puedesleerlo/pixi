"""Coherence (spec §7): style, semantic, structural, transmission — over v5 documents. Read-only.

Semantic coherence: for each active symbol with ≥ 2 tested cards (head version has ≥ ready_threshold human
readings), a per-card effect vector: the paired estimate when the card has an experiment edit on that symbol,
else the pooled residual contribution  (mean reading − intercept − Σ_{j≠s} X_j W_j) / X_s.  Consistent when
every per-card effect is within 45° of the symbol's mean effect; contested otherwise; untested below 2 cards.
coherence_index = consistent / (consistent + contested).
"""
from __future__ import annotations

import math

import numpy as np

from service import measure

ANGLE_DEG = 45.0


def _angle(a: np.ndarray, b: np.ndarray) -> float | None:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return None
    return float(math.degrees(math.acos(float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0)))))


def style(store, deck: dict) -> dict:
    thr = float((deck.get("settings") or {}).get("style_threshold", 0.70))
    cards = {c["id"]: c for c in store.find("cards", deck_id=deck["id"]) if c.get("status") != "archived"}
    scores, outliers = [], []
    for c in cards.values():
        v = store.get("versions", c.get("current_version_id") or "")
        if not v:
            continue
        s = (v.get("checks") or {}).get("style_score")
        if s is None:
            continue
        scores.append(float(s))
        if float(s) < thr:
            outliers.append({"card_id": c["id"], "position_key": c.get("position_key"), "style_score": float(s), "thumb_url": v.get("thumb_url")})
    return {"n": len(scores), "mean": float(np.mean(scores)) if scores else None, "spread": float(np.std(scores)) if scores else None,
            "threshold": thr, "outliers": sorted(outliers, key=lambda x: x["style_score"])}


def semantic(store, deck: dict) -> dict:
    thr = int((deck.get("settings") or {}).get("ready_threshold", 3))
    g = measure.grammar(store, deck["id"])
    syms = measure.active_symbols(store, deck["id"])
    versions = {v["id"]: v for v in store.find("versions", deck_id=deck["id"])}
    cards = [c for c in store.find("cards", deck_id=deck["id"]) if c.get("status") != "archived"]
    # readings per version (human only for testing), intercept-free pooled model uses coef only
    coef = {row["symbol_id"]: np.asarray(row["coef"], dtype=float) for row in g["symbols"]}
    effects_by_symbol: dict[str, list[dict]] = {}
    paired = _paired_by_symbol(store, deck["id"], versions)
    for c in cards:
        v = versions.get(c.get("current_version_id") or "")
        if v is None:
            continue
        rs = measure.human(measure.version_readings(store, v["id"])) or measure.version_readings(store, v["id"])
        if len(rs) < thr:
            continue
        mean = np.mean([r["axes"] for r in rs], axis=0)
        sal = measure.salience_map(v)
        for sid, s in sal.items():
            if sid not in coef or s <= 0:
                continue
            key = (c["id"], sid)
            if key in paired:
                eff, how = paired[key], "paired"
            else:
                others = sum(sal[o] * coef[o] for o in sal if o != sid and o in coef) if len(sal) > 1 else np.zeros(8)
                eff, how = (mean - others) / s, "residual"
            effects_by_symbol.setdefault(sid, []).append({"card_id": c["id"], "position_key": c.get("position_key"), "effect": measure._list(eff), "estimate": how})
    rows, consistent, contested = [], 0, 0
    names = {s["id"]: s for s in syms}
    for s in syms:
        obs = effects_by_symbol.get(s["id"], [])
        if len(obs) < 2:
            rows.append({"symbol_id": s["id"], "name": s.get("name"), "coherence": "untested", "n_cards_tested": len(obs), "cards": obs, "max_angle": None})
            continue
        mean_eff = np.mean([o["effect"] for o in obs], axis=0)
        angles = []
        for o in obs:
            a = _angle(np.asarray(o["effect"]), mean_eff)
            o["angle"] = a
            angles.append(a if a is not None else 0.0)
        status = "consistent" if max(angles) <= ANGLE_DEG else "contested"
        consistent += status == "consistent"
        contested += status == "contested"
        rows.append({"symbol_id": s["id"], "name": s.get("name"), "coherence": status, "n_cards_tested": len(obs), "cards": obs,
                     "mean_effect": measure._list(mean_eff), "max_angle": max(angles),
                     "declared_vs_measured": g["by_id"].get(s["id"], {}).get("declared_vs_measured")})
    idx = consistent / (consistent + contested) if (consistent + contested) else None
    rows.sort(key=lambda r: ({"contested": 0, "consistent": 1, "untested": 2}[r["coherence"]], -(r["max_angle"] or 0)))
    return {"coherence_index": idx, "n_consistent": consistent, "n_contested": contested, "n_untested": len(syms) - consistent - contested, "symbols": rows,
            "angle_threshold": ANGLE_DEG}


def _paired_by_symbol(store, deck_id: str, versions: dict[str, dict]) -> dict[tuple[str, str], np.ndarray]:
    """(card_id, symbol_id) → paired effect from that card's own experiment edits (latest wins)."""
    out: dict[tuple[str, str], np.ndarray] = {}
    readings = store.find("readings", deck_id=deck_id)
    by_version: dict[str, list[dict]] = {}
    for r in readings:
        by_version.setdefault(r["version_id"], []).append(r)
    from pixie.metrics import paired_shift

    for v in sorted(versions.values(), key=lambda x: int(x.get("v", 0))):
        how = v.get("how") or {}
        if how.get("op") not in measure.EXPERIMENT_OPS or not v.get("base_version_id"):
            continue
        base = versions.get(v["base_version_id"])
        if not base:
            continue
        delta, n = paired_shift({r["reader_id"]: r["axes"] for r in by_version.get(base["id"], [])}, {r["reader_id"]: r["axes"] for r in by_version.get(v["id"], [])})
        if delta is None or n == 0:
            continue
        before, after = measure.salience_map(base), measure.salience_map(v)
        for sid in set(before) | set(after):
            ds = after.get(sid, 0.0) - before.get(sid, 0.0)
            if abs(ds) >= 0.05:
                out[(v["card_id"], sid)] = np.asarray(delta, dtype=float) / ds
    return out


def structural(store, deck: dict, positions: list[dict] | None) -> dict:
    cards = [c for c in store.find("cards", deck_id=deck["id"]) if c.get("status") != "archived"]
    by_pos: dict[str, list[dict]] = {}
    for c in cards:
        by_pos.setdefault(c.get("position_key") or "", []).append(c)
    total = len(positions) if positions else None
    filled = len([k for k in by_pos if k]) if positions else len(cards)
    duplicates = [k for k, v in by_pos.items() if k and len(v) > 1]
    empty = [p["key"] for p in (positions or []) if p["key"] not in by_pos]
    drafts_no_intent = [c["id"] for c in cards if c.get("status") == "draft" and not (c.get("intent") or {}).get("statement")]
    closed_not_landed = [c["id"] for c in cards if c.get("status") == "closed"]
    return {"positions_total": total, "positions_filled": filled, "empty_positions": empty, "duplicates": duplicates,
            "drafts_without_intent": drafts_no_intent, "closed_without_landing": closed_not_landed}


def dashboard(store, deck: dict, positions: list[dict] | None = None) -> dict:
    st, se, tr = style(store, deck), semantic(store, deck), measure.transmission(store, deck)
    su = structural(store, deck, positions)
    return {"deck_id": deck["id"], "coherence_index": se["coherence_index"], "style": st, "semantic": se, "structural": su, "transmission": tr,
            "work": {"contested": [r["symbol_id"] for r in se["symbols"] if r["coherence"] == "contested"],
                     "off_style": [o["card_id"] for o in st["outliers"]], "needs_readings": tr["needs_readings"], "empty": su["empty_positions"]}}

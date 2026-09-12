"""Measurement over v5 documents (spec §8): distances, gaps, per-version fidelity, the per-deck grammar
(pooled weighted ridge on detected salience of active symbols), the paired edit-effect estimator,
verdicts, and reveal payloads. Pure functions over the store's dict documents; nothing here writes.

Doc shapes used (spec §3): readings {version_id, card_id, deck_id, reader_id, axes, free_text, embedding, synthetic},
versions {id, card_id, deck_id, v, base_version_id, symbols_detected[{symbol_id, salience}], how{op, symbol_id,
to_symbol_id, bet_axis, counts_as_experiment, editor_id}}, cards {id, intent{statement, axes, embedding?}, status,
maker_id, current_version_id}, symbols {id, key, name, status, declared_axes, prior_axes, prior_source}.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Iterable

import numpy as np

from pixie.axes import AXES, axes_to_words
from pixie.geometry import FrozenPCA
from pixie.grammar import fit_grammar, historical_support
from pixie.metrics import LANDING_F, bet_hit, d_total, fidelity as _fidelity, gaps, landed as _landed, maker_score, paired_shift
from pixie.naming import name_cluster
from pixie.verdict import polysemy_verdict

PLATFORM = {"w_axes": 0.6, "w_embed": 0.4, "radius": 0.30, "v_lo": 0.30, "alpha": 1.0, "w_synthetic": 0.25}
N_BOOT = int(os.environ.get("PIXIE_N_BOOT", "200"))
EXPERIMENT_OPS = {"add", "remove", "replace", "emphasize", "deemphasize", "reposition"}
_lock = threading.RLock()
_grammar_cache: dict[tuple, dict] = {}
_name_cache: dict[tuple, dict] = {}


def _f(x) -> float:
    return float(x)


def _list(a) -> list[float]:
    return [float(v) for v in np.asarray(a, dtype=float).ravel()]


def cfg() -> dict:
    return dict(PLATFORM)


def invalidate(deck_id: str | None = None) -> None:
    with _lock:
        for k in [k for k in _grammar_cache if deck_id is None or k[0] == deck_id]:
            _grammar_cache.pop(k, None)


# ----------------------------------------------------------------------------- basics
def distance(intent: dict, reading: dict) -> dict:
    return d_total(intent["axes"], reading["axes"], intent.get("embedding"), reading.get("embedding"), cfg=cfg())


def human(readings: Iterable[dict]) -> list[dict]:
    return [r for r in readings if not r.get("synthetic")]


def version_readings(store, version_id: str, include_synthetic: bool = True) -> list[dict]:
    rs = store.find("readings", version_id=version_id)
    if not include_synthetic:
        rs = human(rs)
    rs.sort(key=lambda r: r.get("created_at") or "")
    return rs


def salience_map(version: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for s in version.get("symbols_detected") or []:
        if s.get("present", True):
            out[s["symbol_id"]] = max(out.get(s["symbol_id"], 0.0), float(s.get("salience", 0.0)))
    return out


def version_fidelity(card: dict, readings: list[dict]) -> float | None:
    """F_v over human readings; a synthetic-only version (the playground) falls back to its synthetic readings."""
    hs = human(readings) or list(readings)
    if not hs:
        return None
    return _f(_fidelity([distance(card["intent"], r)["d_total"] for r in hs]))


def evaluate_version(card: dict, version: dict, readings: list[dict], prev_readings: list[dict], max_edits: int, threshold_readers: int = 2) -> dict:
    """Spec §8.2/§8.3: fidelity, gaps, maker score (v0), edit effect (v≥1 experiments), landing, next status."""
    intent = card["intent"]
    hs, prev_hs = human(readings), human(prev_readings)
    ds = [distance(intent, r)["d_total"] for r in hs]
    F = _f(_fidelity(ds)) if ds else None
    prev_ds = [distance(intent, r)["d_total"] for r in prev_hs]
    F_prev = _f(_fidelity(prev_ds)) if prev_ds else None
    g_now = gaps(intent["axes"], [r["axes"] for r in hs]) if hs else np.zeros(8)
    g_before = gaps(intent["axes"], [r["axes"] for r in prev_hs]) if prev_hs else None
    how = version.get("how") or {}
    is_edit = bool(how.get("op"))
    ms = maker_score(ds, cfg=cfg()) if not is_edit else None
    effect = None
    if is_edit and how.get("counts_as_experiment", how.get("op") in EXPERIMENT_OPS):
        delta, n_pairs = paired_shift({r["reader_id"]: r["axes"] for r in prev_hs}, {r["reader_id"]: r["axes"] for r in hs})
        k = how.get("bet_axis")
        hit = None
        if k is not None and delta is not None and g_before is not None:
            hit = bool(bet_hit(float(delta[int(k)]), float(g_before[int(k)])))
        effect = {"version_id": version["id"], "n_pairs": int(n_pairs), "shift": _list(delta) if delta is not None else None,
                  "gap_before": _list(g_before) if g_before is not None else None, "gap_after": _list(g_now),
                  "bet_axis": k, "bet_hit": hit, "delta_fidelity": _f(F - F_prev) if (F is not None and F_prev is not None) else None,
                  "points": 2 if hit else 0, "editor_id": how.get("editor_id")}
    landed_now = bool(F is not None and _landed(F, len(hs)))
    status = "landed" if landed_now else ("closed" if int(version.get("v", 0)) >= max_edits else None)
    return {"fidelity": F, "fidelity_prev": F_prev, "delta_fidelity": _f(F - F_prev) if (F is not None and F_prev is not None) else None,
            "gaps_signed": _list(g_now), "gaps_before": _list(g_before) if g_before is not None else None,
            "maker_score": ms, "edit_effect": effect, "landed": landed_now, "landing_threshold": LANDING_F, "next_status": status,
            "n_human": len(hs), "n_synthetic": len(readings) - len(hs)}


# ----------------------------------------------------------------------------- grammar (§8.5)
def active_symbols(store, deck_id: str) -> list[dict]:
    syms = [s for s in store.find("symbols", deck_id=deck_id) if s.get("status", "active") == "active"]
    syms.sort(key=lambda s: s.get("key") or s["id"])
    return syms


def grammar(store, deck_id: str, include_synthetic: bool = True, exclude_version_ids: Iterable[str] = ()) -> dict:
    """Pooled weighted ridge of reading axes on detected salience of the deck's active symbols."""
    excl = frozenset(exclude_version_ids)
    readings = store.find("readings", deck_id=deck_id)
    if not include_synthetic:
        readings = human(readings)
    readings = [r for r in readings if r["version_id"] not in excl]
    syms = active_symbols(store, deck_id)
    key = (deck_id, len(readings), include_synthetic, excl, len(syms), PLATFORM["alpha"], PLATFORM["w_synthetic"])
    with _lock:
        if key in _grammar_cache:
            return _grammar_cache[key]
    pos = {s["id"]: j for j, s in enumerate(syms)}
    E = len(syms)
    versions = {v["id"]: v for v in store.find("versions", deck_id=deck_id)}
    X, Y, W, used = [], [], [], []
    for r in readings:
        v = versions.get(r["version_id"])
        if v is None:
            continue
        row = np.zeros(E)
        for sid, sal in salience_map(v).items():
            j = pos.get(sid)
            if j is not None:
                row[j] = sal
        X.append(row)
        Y.append(r["axes"])
        W.append(PLATFORM["w_synthetic"] if r.get("synthetic") else 1.0)
        used.append(r)
    if len(X) < 3 or E == 0:
        fit = {"coef": np.zeros((E, 8)), "ci_low": np.zeros((E, 8)), "ci_high": np.zeros((E, 8)), "n": len(X)}
    else:
        w = W if any(x != 1.0 for x in W) else None
        fit = fit_grammar(np.array(X), np.array(Y, dtype=float), alpha=float(PLATFORM["alpha"]), n_boot=N_BOOT, seed=0, sample_weight=w)
    coef, lo, hi = np.asarray(fit["coef"]), np.asarray(fit["ci_low"]), np.asarray(fit["ci_high"])
    effects = edit_effects(store, deck_id, versions=versions, readings=used)
    rows, by_id = [], {}
    n_cards_by_symbol: dict[str, set] = {}
    for v in versions.values():
        for sid in salience_map(v):
            n_cards_by_symbol.setdefault(sid, set()).add(v["card_id"])
    for j, s in enumerate(syms):
        prior = s.get("prior_axes")
        eff = effects.get(s["id"]) or {}
        c = _list(coef[j]) if E else []
        row = {"symbol_id": s["id"], "key": s.get("key"), "name": s.get("name"), "coef": c, "ci_low": _list(lo[j]) if E else [],
               "ci_high": _list(hi[j]) if E else [], "n_readings": int(fit["n"]), "n_edits": int(eff.get("n_edits", 0)),
               "mean_effect": eff.get("mean_effect"), "n_cards": len(n_cards_by_symbol.get(s["id"], ())),
               "prior_axes": _list(prior) if prior else None, "prior_source": s.get("prior_source"),
               "drift_from_prior": _f(1.0 - historical_support(coef[j], prior)) if prior else None,
               "declared_vs_measured": _f(historical_support(coef[j], s.get("declared_axes") or [0] * 8)) if s.get("declared_axes") else None}
        rows.append(row)
        by_id[s["id"]] = row
    n_syn = sum(1 for r in used if r.get("synthetic"))
    out = {"deck_id": deck_id, "axes": [list(a) for a in AXES], "n_readings": len(used), "n_real": len(used) - n_syn, "n_synthetic": n_syn,
           "n_edits": sum(1 for v in versions.values() if (v.get("how") or {}).get("op") in EXPERIMENT_OPS),
           "alpha": PLATFORM["alpha"], "n_boot": N_BOOT, "w_synthetic": PLATFORM["w_synthetic"], "symbols": rows, "by_id": by_id}
    with _lock:
        _grammar_cache[key] = out
    return out


def edit_effects(store, deck_id: str, versions: dict[str, dict] | None = None, readings: list[dict] | None = None) -> dict[str, dict]:
    """Paired observations from experiment edits: shift / Δsalience per symbol (spec §8.5)."""
    versions = versions if versions is not None else {v["id"]: v for v in store.find("versions", deck_id=deck_id)}
    readings = readings if readings is not None else store.find("readings", deck_id=deck_id)
    by_version: dict[str, list[dict]] = {}
    for r in readings:
        by_version.setdefault(r["version_id"], []).append(r)
    acc: dict[str, list[np.ndarray]] = {}
    for v in versions.values():
        how = v.get("how") or {}
        if how.get("op") not in EXPERIMENT_OPS or not v.get("base_version_id"):
            continue
        base = versions.get(v["base_version_id"])
        if base is None:
            continue
        delta, n_pairs = paired_shift({r["reader_id"]: r["axes"] for r in by_version.get(base["id"], [])},
                                      {r["reader_id"]: r["axes"] for r in by_version.get(v["id"], [])})
        if delta is None or n_pairs == 0:
            continue
        before, after = salience_map(base), salience_map(v)
        for sid in set(before) | set(after):
            ds = after.get(sid, 0.0) - before.get(sid, 0.0)
            if abs(ds) >= 0.05:
                acc.setdefault(sid, []).append(np.asarray(delta, dtype=float) / ds)
    return {sid: {"n_edits": len(obs), "mean_effect": _list(np.mean(obs, axis=0))} for sid, obs in acc.items()}


def grammar_strip(store, deck_id: str, version: dict, exclude_version_ids: Iterable[str] = ()) -> list[dict]:
    g = grammar(store, deck_id, True, exclude_version_ids)["by_id"]
    strip = []
    for sid, sal in sorted(salience_map(version).items(), key=lambda x: -x[1]):
        row = g.get(sid)
        if row:
            strip.append({**{k: row[k] for k in ("symbol_id", "key", "name", "coef", "ci_low", "ci_high", "n_readings", "n_edits", "drift_from_prior")}, "salience": sal})
    return strip


# ----------------------------------------------------------------------------- verdict (§8.4)
def verdict(store, deck_id: str, version: dict) -> dict:
    rs = version_readings(store, version["id"])
    hs = human(rs)
    use = hs if len(hs) >= 8 else rs  # synthetic decks have only synthetic readings
    base = {"version_id": version["id"], "card_id": version["card_id"], "n_human": len(hs), "n_synthetic": len(rs) - len(hs)}
    if len(use) < 8:
        return {**base, "verdict": "collecting", "n": len(use), "needed": 8}
    axes = np.array([r["axes"] for r in use], dtype=float)
    v = {**base, **polysemy_verdict(axes, v_lo=float(PLATFORM["v_lo"]), n_null=200, seed=0, cfg=cfg())}
    if v.get("verdict") == "polysemous":
        g = grammar(store, deck_id)["by_id"]
        tops = sorted(((sal * float(np.linalg.norm(g[sid]["coef"])), g[sid]["name"] or sid) for sid, sal in salience_map(version).items() if sid in g), reverse=True)[:2]
        for ci, cl in enumerate(v.get("clusters", [])):
            texts = [use[i].get("free_text") for i in cl.get("member_idx", []) if use[i].get("free_text")]
            key = (version["id"], len(use), ci)
            if key not in _name_cache:
                _name_cache[key] = name_cluster(texts, np.asarray(cl["centroid"]), [t[1] for t in tops])
            cl["label"], cl["label_by"] = _name_cache[key]["label"], _name_cache[key]["by"]
    return v


# ----------------------------------------------------------------------------- geometry
def pca(store) -> FrozenPCA | None:
    doc = store.get("pca", "pca")
    return FrozenPCA.from_dict(doc) if doc else None


def ensure_pca(store, points: np.ndarray) -> FrozenPCA:
    p = pca(store)
    if p is None:
        p = FrozenPCA().fit(points)
        store.put("pca", {"id": "pca", **p.to_dict()})
    return p


# ----------------------------------------------------------------------------- reveal (§5.8, §4.5 Readings tab)
def reveal(store, deck: dict, card: dict, version: dict, viewer_id: str | None, encoder: bool, readings: list[dict] | None = None,
           prev_readings: list[dict] | None = None, ready_threshold: int | None = None) -> dict:
    """Reveal payload for one version. Readers never get the statement or signed gaps until the card is
    landed/closed; the intent star is shown once `ready_threshold` human readings exist (spec §5.8)."""
    ready_threshold = ready_threshold or int((deck.get("settings") or {}).get("ready_threshold", 3))
    max_edits = int((deck.get("settings") or {}).get("max_edits_per_card", 6))
    rs = readings if readings is not None else version_readings(store, version["id"])
    prev = None
    if version.get("base_version_id"):
        prev = store.get("versions", version["base_version_id"])
    prev_rs = prev_readings if prev_readings is not None else (version_readings(store, prev["id"]) if prev else [])
    res = evaluate_version(card, version, rs, prev_rs, max_edits)
    intent = card["intent"]
    pts = np.array([intent["axes"]] + [r["axes"] for r in rs] + [r["axes"] for r in prev_rs], dtype=float)
    p = pca(store)
    xy = p.transform(pts) if p is not None else np.zeros((len(pts), 2))
    prev_by_reader = {r["reader_id"]: (r, xy[1 + len(rs) + i]) for i, r in enumerate(prev_rs)}
    items, you = [], {"d_total": None, "shift": None}
    for k, r in enumerate(rs):
        d = distance(intent, r)
        pr = prev_by_reader.get(r["reader_id"])
        shift = _list(np.asarray(r["axes"]) - np.asarray(pr[0]["axes"])) if pr else None
        items.append({"reader_id": r.get("reader_id") if encoder else None, "nickname": r.get("nickname") if encoder else None,
                      "axes": r["axes"], "free_text": r.get("free_text"), **d, "xy": _list(xy[k + 1]), "prev_xy": _list(pr[1]) if pr else None,
                      "prev_axes": pr[0]["axes"] if pr else None, "shift": shift, "synthetic": bool(r.get("synthetic")), "is_you": r.get("reader_id") == viewer_id})
        if r.get("reader_id") == viewer_id:
            you = {"d_total": d["d_total"], "shift": shift}
    public = card.get("status") in ("landed", "closed")
    show_star = encoder or res["n_human"] >= ready_threshold or public
    g_abs = sorted(({"axis": i, "abs": abs(v), "poles": list(AXES[i])} for i, v in enumerate(res["gaps_signed"])), key=lambda x: -x["abs"])
    return {"card": {"id": card["id"], "status": card.get("status"), "title": card.get("title"), "position_key": card.get("position_key"),
                     "v": int(version.get("v", 0)), "max_edits": max_edits, "landed": res["landed"],
                     "statement": intent["statement"] if (public or encoder) else None},
            "version": {"id": version["id"], "v": int(version.get("v", 0)), "image_url": version.get("image_url"), "thumb_url": version.get("thumb_url"),
                        "symbols_detected": version.get("symbols_detected", []), "how": version.get("how")},
            "intent_xy": _list(xy[0]) if show_star else None, "radius": PLATFORM["radius"], "readings": items,
            "fidelity": res["fidelity"], "fidelity_prev": res["fidelity_prev"], "delta_fidelity": res["delta_fidelity"],
            "gaps_abs": g_abs if show_star else None, "gaps_signed": res["gaps_signed"] if encoder else None,
            "maker_score": res["maker_score"] if encoder or public else None, "edit_effect": res["edit_effect"],
            "landing": {"landed": True, "threshold": LANDING_F} if res["landed"] else None,
            "verdict": verdict(store, deck["id"], version), "grammar_strip": grammar_strip(store, deck["id"], version),
            "grammar_strip_before": grammar_strip(store, deck["id"], version, exclude_version_ids=[version["id"]]),
            "collecting": {"n": res["n_human"], "threshold": ready_threshold}, "you": you}


# ----------------------------------------------------------------------------- transmission summary (§7.4)
def transmission(store, deck: dict) -> dict:
    cards = [c for c in store.find("cards", deck_id=deck["id"]) if c.get("status") != "archived"]
    versions = {v["id"]: v for v in store.find("versions", deck_id=deck["id"])}
    per_card, verdicts, buckets = [], {"legible": 0, "polysemous": 0, "noisy": 0, "collecting": 0}, {}
    needs = []
    thr = int((deck.get("settings") or {}).get("ready_threshold", 3))
    for c in cards:
        v = versions.get(c.get("current_version_id") or "")
        if v is None:
            continue
        rs = version_readings(store, v["id"])
        F = version_fidelity(c, rs)
        n_h = len(human(rs))
        vd = verdict(store, deck["id"], v)
        verdicts[vd["verdict"]] = verdicts.get(vd["verdict"], 0) + 1
        per_card.append({"card_id": c["id"], "position_key": c.get("position_key"), "status": c.get("status"), "fidelity": F,
                         "n_human": n_h, "verdict": vd["verdict"], "n_symbols": len(salience_map(v))})
        if n_h < thr and c.get("status") in ("reading", "draft"):
            needs.append(c["id"])
        if F is not None:
            buckets.setdefault(len(salience_map(v)), []).append(F)
    done = [x["fidelity"] for x in per_card if x["status"] in ("landed", "closed") and x["fidelity"] is not None]
    return {"mean_fidelity": _f(np.mean(done)) if done else None, "verdicts": verdicts, "needs_readings": needs, "cards": per_card,
            "bandwidth": [{"n_symbols": k, "mean_fidelity": _f(np.mean(v)), "n_cards": len(v)} for k, v in sorted(buckets.items())]}

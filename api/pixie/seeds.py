"""Seed data IS the estimator test (spec v4 §6.7).

Planted grammar W* = the historical priors of the base library, so at t = 0 the deck reads exactly
as the tradition does. 60 synthetic composed cards (2–5 slotted elements), 300 v0 readings
    axes = clip(X_version @ W* + N(0, noise_sd), -3, 3),
40 synthetic one-move edits, each read by 4 paired readers on BOTH versions
    reading(v1) = reading(v0) + Δrow @ W* + N(0, PAIRED_SD),
one planted POLYSEMOUS card (two modes) and one planted NOISY card (isotropic scatter) with matched V.
Everything is flagged synthetic=True and lives in one deck.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

import numpy as np

from .axes import AXES, AXIS_MAX, N_AXES, axes_to_words
from .data import element_priors, placeable
from .slots import FILL_ORDER, MAX_ELEMENTS, MIN_ELEMENTS, SLOTS, apply_move, auto_assign, design_row, describe_move, free_slots, may_occupy
from .verdict import _real_clustering, null_s95, raw_variance

BASE_TIME = datetime(2026, 9, 12, 0, 0, 0, tzinfo=timezone.utc)
PLANTED_N = 12          # readings on each planted card's v0
POLY_SEP = 4.5          # half-distance between the two modes (raw −3..3 units, along a unit direction)
POLY_SD = 0.35          # within-mode sd
PAIRED_SD = 0.30        # extra noise on a paired reader's second read
NOISY_TRIES = 5         # redraws allowed for the noisy plant (an isotropic draw fails the null 5 % of the time)
MIN_COVERAGE = 3        # every placeable element on ≥ this many cards
N_ROUND_ROBIN_READERS = 20
MOVE_WEIGHTS = {"add": 0.35, "remove": 0.25, "swap": 0.25, "move": 0.15}
MAKER_ID, EDITOR_ID = "g_seed_maker", "g_seed_editor"


def _clip(a: np.ndarray) -> np.ndarray:
    return np.clip(a, -AXIS_MAX, AXIS_MAX)


def _iso(i: int) -> str:
    return (BASE_TIME + timedelta(seconds=i)).isoformat().replace("+00:00", "Z")


def _pole(k: int, sign: float) -> str:
    return AXES[k][0] if sign < 0 else AXES[k][1]


def _compose_cards(rng: np.random.Generator, place: list[dict], n_cards: int) -> list[list[dict]]:
    """Random 2–5-element pick lists, every element on ≥ MIN_COVERAGE cards, all auto-assignable."""
    ids = [e["id"] for e in place]
    by_id = {e["id"]: e for e in place}
    picks: list[list[str]] = []
    for _ in range(n_cards):
        k = int(rng.choice([2, 3, 4, 5], p=[0.15, 0.35, 0.30, 0.20]))
        chosen = list(rng.choice(ids, size=k, replace=False))
        if not any(by_id[c]["size_class"] == "large" for c in chosen):
            chosen = chosen[:4]
        picks.append(chosen)
    # coverage fix-up: add under-covered elements to cards that can still take them
    for _ in range(10 * len(ids)):
        counts = {i: 0 for i in ids}
        for p in picks:
            for c in p:
                counts[c] += 1
        under = [i for i in ids if counts[i] < MIN_COVERAGE]
        if not under:
            break
        for eid in under:
            order = rng.permutation(len(picks))
            for ci in order:
                p = picks[ci]
                if eid in p or len(p) >= MAX_ELEMENTS:
                    continue
                cand = p + [eid]
                has_large = any(by_id[c]["size_class"] == "large" for c in cand)
                if not has_large and len(cand) > 4:
                    continue
                picks[ci] = cand
                break
    return [[by_id[c] for c in p] for p in picks]


def _random_move(rng: np.random.Generator, elements: list[dict], place: list[dict], by_id: dict) -> Optional[dict]:
    """One random legal move for a version, or None after 30 failed attempts."""
    on = [it["element_id"] for it in elements]
    off = [e["id"] for e in place if e["id"] not in on]
    kinds = list(MOVE_WEIGHTS)
    probs = np.array([MOVE_WEIGHTS[k] for k in kinds])
    for _ in range(30):
        kind = str(rng.choice(kinds, p=probs / probs.sum()))
        move: dict
        if kind == "add":
            if len(elements) >= MAX_ELEMENTS or not off:
                continue
            move = {"type": "add", "element_id": str(rng.choice(off)), "to_slot": None}
        elif kind == "remove":
            if len(elements) <= MIN_ELEMENTS:
                continue
            move = {"type": "remove", "element_id": str(rng.choice(on))}
        elif kind == "swap":
            eid = str(rng.choice(on))
            slot = next(it["slot"] for it in elements if it["element_id"] == eid)
            cands = [o for o in off if may_occupy(by_id[o]["size_class"], slot)]
            if not cands:
                continue
            move = {"type": "swap", "element_id": eid, "to_element_id": str(rng.choice(cands))}
        else:
            eid = str(rng.choice(on))
            cands = [s for s in free_slots(elements) if may_occupy(by_id[eid]["size_class"], s)]
            if not cands:
                continue
            move = {"type": "move", "element_id": eid, "to_slot": str(rng.choice(cands))}
        try:
            apply_move(elements, move, by_id)
        except ValueError:
            continue
        return move
    return None


def generate_seeds(
    elements: Sequence[dict],
    n_cards: int = 60,
    n_readings: int = 300,
    n_edits: int = 40,
    paired: int = 4,
    noise_sd: float = 0.8,
    seed: int = 0,
    deck_id: str = "playground",
) -> dict:
    rng = np.random.default_rng(seed)
    place = sorted(placeable(elements), key=lambda e: e["id"])
    if len(place) < 6:
        raise ValueError("generate_seeds needs a library with at least 6 placeable elements")
    leaf = [e["id"] for e in place]
    leaf_pos = {eid: j for j, eid in enumerate(leaf)}
    E = len(leaf)
    by_id = {e["id"]: e for e in elements}
    W_star = element_priors(elements, leaf)  # (E, 8)

    # ---------------------------------------------------------------- cards + v0
    pick_lists = _compose_cards(rng, place, n_cards)
    cards, versions, readings = [], [], []
    v0_of: dict[str, dict] = {}
    X0 = np.zeros((n_cards, E))
    for i, picked in enumerate(pick_lists):
        cid, vid = f"c_seed_{i:03d}", f"v_seed_{i:03d}_0"
        els = auto_assign(picked)
        X0[i] = design_row(els, leaf_pos, E)
        mu = _clip(X0[i] @ W_star)
        labels = [by_id[it["element_id"]]["label"].lower() for it in els[:3]]
        stmt = f"reads {axes_to_words(mu, 3) or 'neutral'} — {', '.join(labels)}"
        cards.append({
            "id": cid, "deck_id": deck_id, "mode": "room", "room_id": None,
            "maker_id": MAKER_ID, "maker_nickname": "seed maker",
            "intent": {"statement": stmt[:140], "axes": [float(round(v, 3)) for v in mu], "embedding": None},
            "approved_editors": "*", "status": "closed", "title": None, "title_by": None,
            "latest_version_id": vid, "n_versions": 1, "encoder_ids": [MAKER_ID],
            "created_at": _iso(i), "finished_at": _iso(i), "synthetic": True, "seed_planted": None,
        })
        v0 = {"id": vid, "card_id": cid, "deck_id": deck_id, "v": 0, "elements": els, "edit": None,
              "created_at": _iso(i), "synthetic": True}
        versions.append(v0)
        v0_of[cid] = v0
    mu_all = _clip(X0 @ W_star)

    # planted cards: the two with the fewest elements-in-common with each other among cards 0..n-1 is overkill;
    # take deterministic positions away from the edited block (edits use the first n_edits non-planted cards)
    poly_i = n_cards - 2
    noisy_i = n_cards - 1
    poly_id, noisy_id = cards[poly_i]["id"], cards[noisy_i]["id"]
    cards[poly_i]["seed_planted"] = "polysemous"
    cards[noisy_i]["seed_planted"] = "noisy"

    # ---------------------------------------------------------------- v0 readings
    r = 0
    per_card_axes: dict[str, list] = {c["id"]: [] for c in cards}

    def add_reading(card: dict, version_id: str, reader_id: str, nickname: str, axes: np.ndarray,
                    text: Optional[str] = None, mode: Optional[str] = None) -> dict:
        nonlocal r
        rec = {
            "id": f"r_seed_{r:04d}", "deck_id": deck_id, "card_id": card["id"], "version_id": version_id,
            "reader_id": reader_id, "nickname": nickname, "room_id": None, "round_id": "seed",
            "free_text": text, "axes": [float(round(v, 3)) for v in axes], "embedding": None,
            "latency_ms": None, "synthetic": True, "model": False, "created_at": _iso(1000 + r),
        }
        if mode:
            rec["planted_mode"] = mode
        readings.append(rec)
        if version_id == v0_of[card["id"]]["id"]:
            per_card_axes[card["id"]].append(np.asarray(axes, dtype=float))
        r += 1
        return rec

    counts = {c["id"]: 0 for c in cards}
    counts[poly_id] = PLANTED_N
    counts[noisy_id] = PLANTED_N
    others = [c["id"] for c in cards if c["id"] not in (poly_id, noisy_id)]
    for k in range(max(n_readings - 2 * PLANTED_N, 0)):
        counts[others[k % len(others)]] += 1
    for i, c in enumerate(cards):
        if c["id"] in (poly_id, noisy_id):
            continue
        for _ in range(counts[c["id"]]):
            rid = r % N_ROUND_ROBIN_READERS
            add_reading(c, v0_of[c["id"]]["id"], f"g_seed_r{rid:02d}", f"seed reader {rid}",
                        _clip(mu_all[i] + rng.normal(0.0, noise_sd, N_AXES)))

    # planted polysemous: two modes at center ± POLY_SEP·d, d spread over the 3 axes with the most room
    center = mu_all[poly_i] * 0.5
    d_idx = np.argsort(np.abs(mu_all[poly_i]), kind="stable")[:3]
    d = np.zeros(N_AXES); d[d_idx] = 1.0 / np.sqrt(3.0)
    center[d_idx] = 0.0
    modes = {"A": center + POLY_SEP * d, "B": center - POLY_SEP * d}
    for t in range(counts[poly_id]):
        m = "A" if t % 2 == 0 else "B"
        rid = r % N_ROUND_ROBIN_READERS
        add_reading(cards[poly_i], v0_of[poly_id]["id"], f"g_seed_r{rid:02d}", f"seed reader {rid}",
                    _clip(modes[m] + rng.normal(0.0, POLY_SD, N_AXES)), f"reads as {axes_to_words(modes[m], 2)}", mode=m)
    V_poly = raw_variance(np.stack(per_card_axes[poly_id]) / AXIS_MAX)

    # planted noisy: isotropic scatter rescaled so V matches V_poly; redraw if the draw happens to beat the null
    ncenter = mu_all[noisy_i] * 0.5
    pts = None
    for _try in range(NOISY_TRIES):
        Z = rng.normal(0.0, 1.0, (counts[noisy_id], N_AXES))
        s = 1.0
        for _ in range(6):
            cand = _clip(ncenter + s * Z)
            v = raw_variance(cand / AXIS_MAX)
            if v <= 1e-9:
                break
            s *= V_poly / v
        pts = _clip(ncenter + s * Z)
        if _real_clustering(pts / AXIS_MAX, seed)[1] <= null_s95(len(pts)):
            break
    for t in range(counts[noisy_id]):
        rid = r % N_ROUND_ROBIN_READERS
        add_reading(cards[noisy_i], v0_of[noisy_id]["id"], f"g_seed_r{rid:02d}", f"seed reader {rid}", pts[t], None, mode="noise")
    V_noisy = raw_variance(pts / AXIS_MAX)

    # ---------------------------------------------------------------- edits with paired readers
    edited = 0
    edit_summaries = []
    for i, c in enumerate(cards):
        if edited >= n_edits:
            break
        if c["id"] in (poly_id, noisy_id):
            continue
        v0 = v0_of[c["id"]]
        move = _random_move(rng, v0["elements"], place, by_id)
        if move is None:
            continue
        new_els = apply_move(v0["elements"], move, by_id)
        row0, row1 = X0[i], design_row(new_els, leaf_pos, E)
        expected = (row1 - row0) @ W_star
        bet = int(np.argmax(np.abs(expected)))
        vid1 = f"v_seed_{i:03d}_1"
        edit = {
            "type": move["type"], "element_id": move["element_id"],
            "to_element_id": move.get("to_element_id"), "to_slot": move.get("to_slot"),
            "editor_id": EDITOR_ID, "editor_nickname": "seed editor", "bet_axis": bet,
            "rationale": f"{describe_move(move, by_id)}; expecting a move toward {_pole(bet, expected[bet])}"[:140],
        }
        if move["type"] == "add" and move.get("to_slot") is None:  # record the slot auto-assignment chose
            edit["to_slot"] = next(it["slot"] for it in new_els if it["element_id"] == move["element_id"])
        versions.append({"id": vid1, "card_id": c["id"], "deck_id": deck_id, "v": 1, "elements": new_els,
                         "edit": edit, "created_at": _iso(500 + i), "synthetic": True})
        c["latest_version_id"] = vid1
        c["n_versions"] = 2
        c["encoder_ids"] = [MAKER_ID, EDITOR_ID]
        for p in range(paired):
            reader_id = f"g_seed_p{p:02d}"
            base = _clip(mu_all[i] + rng.normal(0.0, noise_sd, N_AXES))
            add_reading(c, v0["id"], reader_id, f"paired reader {p}", base)
            add_reading(c, vid1, reader_id, f"paired reader {p}", _clip(base + expected + rng.normal(0.0, PAIRED_SD, N_AXES)))
        edit_summaries.append({"card_id": c["id"], "version_id": vid1, "type": move["type"],
                               "element_id": move["element_id"], "to_element_id": move.get("to_element_id"),
                               "bet_axis": bet, "expected_shift": [float(x) for x in expected]})
        edited += 1

    vs = [raw_variance(np.stack(per_card_axes[cid]) / AXIS_MAX)
          for cid in others if len(per_card_axes[cid]) >= 4]
    V_lo = float(np.median(vs)) if vs else 0.30

    return {
        "cards": cards,
        "versions": versions,
        "readings": readings,
        "planted": {
            "W_star": {eid: [float(v) for v in W_star[j]] for j, eid in enumerate(leaf)},
            "leaf_element_ids": list(leaf),
            "polysemous_card_id": poly_id,
            "noisy_card_id": noisy_id,
            "polysemous_version_id": v0_of[poly_id]["id"],
            "noisy_version_id": v0_of[noisy_id]["id"],
            "V_lo": V_lo,
            "V_polysemous": float(V_poly),
            "V_noisy": float(V_noisy),
            "noise_sd": float(noise_sd),
            "paired_sd": float(PAIRED_SD),
            "n_cards": len(cards),
            "n_readings": len(readings),
            "n_v0_readings": int(sum(1 for x in readings if x["version_id"].endswith("_0"))),
            "n_edits": edited,
            "edits": edit_summaries,
            "seed": int(seed),
            "deck_id": deck_id,
        },
    }


def seed_design(versions: Sequence[dict], readings: Sequence[dict], leaf_ids: Sequence[str]):
    """Rows (X, Y) for fit_grammar from any readings: X = slot salience of the version each reading read."""
    from .data import design_matrix_versions

    vbyid = {v["id"]: v for v in versions}
    rows = [rd for rd in readings if rd["version_id"] in vbyid]
    X = design_matrix_versions([vbyid[rd["version_id"]] for rd in rows], leaf_ids)
    Y = np.asarray([rd["axes"] for rd in rows], dtype=float).reshape(-1, N_AXES)
    return X, Y

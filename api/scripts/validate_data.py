"""Validate data/cards.json, data/elements.json, data/card_elements.json.

Run:  api/.venv/bin/python api/scripts/validate_data.py   (exit 1 on any hard failure)
Checks: schemas, 44 cards, sibling symmetry, >=3 tags per card, every leaf used on >=2 cards,
no unknown ids, priors in range, leaf-prior matrix rank 8, always-co-occurring element pairs
(shared CI warning), design-matrix rank vs number of leaf elements.
"""
from __future__ import annotations
import itertools, json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CARD_KEYS = {"id", "title", "arcana", "number", "image_url", "thumb_url", "source_deck", "source_year",
             "rights_note", "caption", "commons_title", "sibling_ids"}
EL_KEYS = {"id", "label", "gloss", "parent_id", "historical_prior", "prior_coded_by", "attestations"}
TAG_KEYS = {"card_id", "element_id", "visual_salience", "tagged_by"}

errors, warnings = [], []
err = errors.append
warn = warnings.append


def main() -> int:
    cards = json.loads((DATA / "cards.json").read_text())
    elements = json.loads((DATA / "elements.json").read_text())
    tags = json.loads((DATA / "card_elements.json").read_text())

    # ---- cards
    if len(cards) != 44:
        err(f"expected 44 cards, got {len(cards)}")
    cid = {}
    for c in cards:
        missing = CARD_KEYS - set(c)
        if missing:
            err(f"card {c.get('id')} missing keys {sorted(missing)}")
        if c["id"] in cid:
            err(f"duplicate card id {c['id']}")
        cid[c["id"]] = c
        for s in ("title", "caption", "rights_note", "source_deck"):
            if any(bad in str(c.get(s, "")).lower() for bad in ("rider-waite", "rider waite", "rider–waite", "rider tarot")):
                err(f"card {c['id']}: '{s}' mentions the trademarked name")
        if not c["caption"] or "·" not in c["caption"]:
            err(f"card {c['id']}: caption must read 'artist, year · rights'")
        if c["source_deck"] not in ("Smith 1909", "Conver 1760"):
            err(f"card {c['id']}: unknown source_deck {c['source_deck']}")
    for c in cards:
        sibs = c["sibling_ids"]
        if len(sibs) != 1:
            err(f"card {c['id']}: expected exactly one sibling, got {sibs}")
            continue
        s = cid.get(sibs[0])
        if s is None:
            err(f"card {c['id']}: sibling {sibs[0]} unknown")
        elif s["sibling_ids"] != [c["id"]]:
            err(f"sibling asymmetry {c['id']} -> {sibs[0]} -> {s['sibling_ids']}")
        elif s["source_deck"] == c["source_deck"]:
            err(f"card {c['id']}: sibling {sibs[0]} is in the same deck")

    # ---- elements
    eid = {}
    for e in elements:
        missing = EL_KEYS - set(e)
        if missing:
            err(f"element {e.get('id')} missing keys {sorted(missing)}")
        if e["id"] in eid:
            err(f"duplicate element id {e['id']}")
        eid[e["id"]] = e
        p = e["historical_prior"]
        if len(p) != 8 or any(not (-3 <= float(x) <= 3) for x in p):
            err(f"element {e['id']}: prior must be 8 floats in -3..3")
        if e["prior_coded_by"] not in ("human", "k2-drafted, human-approved"):
            err(f"element {e['id']}: bad prior_coded_by")
    for e in elements:
        if e["parent_id"] is not None:
            par = eid.get(e["parent_id"])
            if par is None:
                err(f"element {e['id']}: unknown parent {e['parent_id']}")
            elif par["parent_id"] is not None:
                err(f"element {e['id']}: parent {e['parent_id']} is not top-level (two levels only)")
            if not e["attestations"]:
                err(f"leaf element {e['id']}: needs >=1 attestation")
            for a in e["attestations"]:
                if a.get("card_id") not in cid:
                    err(f"element {e['id']}: attestation cites unknown card {a.get('card_id')}")
                if a.get("source") not in ("Waite 1911", "Marseille tradition"):
                    err(f"element {e['id']}: attestation source must be 'Waite 1911' or 'Marseille tradition'")
    leaves = [e for e in elements if e["parent_id"] is not None]
    parents = [e for e in elements if e["parent_id"] is None]
    P = np.array([e["historical_prior"] for e in leaves], dtype=float)
    if np.allclose(P, P[0]):
        err("all leaf priors identical")
    prank = np.linalg.matrix_rank(P)
    if prank < 8:
        err(f"leaf prior matrix rank {prank} < 8")

    # ---- tags
    per_card: dict[str, dict[str, float]] = {}
    for t in tags:
        missing = TAG_KEYS - set(t)
        if missing:
            err(f"tag {t} missing keys {sorted(missing)}")
            continue
        if t["card_id"] not in cid:
            err(f"tag cites unknown card {t['card_id']}")
        e = eid.get(t["element_id"])
        if e is None:
            err(f"tag on {t['card_id']} cites unknown element {t['element_id']}")
        elif e["parent_id"] is None:
            err(f"tag on {t['card_id']} uses top-level group {t['element_id']} (tag leaves only)")
        if not (0 <= float(t["visual_salience"]) <= 1):
            err(f"tag {t['card_id']}/{t['element_id']}: salience out of range")
        if t["tagged_by"] not in ("human", "gemini"):
            err(f"tag {t['card_id']}/{t['element_id']}: bad tagged_by")
        d = per_card.setdefault(t["card_id"], {})
        if t["element_id"] in d:
            err(f"duplicate tag {t['card_id']}/{t['element_id']}")
        d[t["element_id"]] = float(t["visual_salience"])
    for c in cards:
        d = per_card.get(c["id"], {})
        if len(d) < 3:
            err(f"card {c['id']}: only {len(d)} tags (need >=3)")
        elif len(set(d.values())) < 2:
            warn(f"card {c['id']}: all saliences identical")
    leaf_ids = sorted(e["id"] for e in leaves)
    usage = {l: sorted(c for c, d in per_card.items() if l in d) for l in leaf_ids}
    for l, cs in usage.items():
        if len(cs) < 2:
            err(f"leaf element {l}: used on {len(cs)} card(s), need >=2")

    # ---- design matrix + co-occurrence
    used = [l for l in leaf_ids if usage[l]]
    X = np.array([[per_card.get(c["id"], {}).get(l, 0.0) for l in used] for c in cards])
    B = X > 0
    xrank = np.linalg.matrix_rank(X)
    always = []
    for a, b in itertools.combinations(range(len(used)), 2):
        if np.array_equal(B[:, a], B[:, b]):
            always.append((used[a], used[b], int(B[:, a].sum())))
    nested = []
    for a, b in itertools.permutations(range(len(used)), 2):
        if B[:, a].sum() >= 2 and np.all(B[:, a] <= B[:, b]) and not np.array_equal(B[:, a], B[:, b]):
            nested.append((used[a], used[b]))

    # ---- report
    print(f"cards: {len(cards)}   elements: {len(elements)} ({len(parents)} groups, {len(leaves)} leaves, {len(used)} used)   tags: {len(tags)}")
    print(f"tags per card: min {min(len(v) for v in per_card.values())}  max {max(len(v) for v in per_card.values())}  mean {len(tags)/len(cards):.1f}")
    print(f"leaf-prior matrix rank: {prank} / 8")
    print(f"design matrix (44 x {len(used)}) rank: {xrank}  -> {len(used) - xrank} element direction(s) not separable from the corpus alone")
    print("element usage (cards):", ", ".join(f"{l}={len(usage[l])}" for l in used))
    if always:
        print("ALWAYS co-occurring pairs (identical presence columns; they will share a wide CI):")
        for a, b, n in always:
            print(f"  {a} <-> {b}  (on {n} cards)")
    else:
        print("always co-occurring pairs: none")
    if nested:
        print(f"nested pairs (A only ever appears with B; {len(nested)}): " + ", ".join(f"{a}⊂{b}" for a, b in nested[:40]))
    for w in warnings:
        print("WARN", w)
    for e in errors:
        print("ERROR", e)
    print("OK" if not errors else f"FAILED with {len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

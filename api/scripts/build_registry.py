"""Build data/base_decks/<slug>/registry.json (spec v5 §3.6 Symbol drafts) from the v4 element sheets.

Idempotent. Inputs: data/libraries/<slug>/elements.json (symbols with bbox crops, priors, attestations),
data/card_elements.json (per-card salience tags, v4 ids) and the Appendix B additions below for Smith.
Output doc: {slug, version, symbols: [Symbol draft], symbols_by_card: {position_key: [{key, salience}]}}
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "base_decks")
LIBS = {"smith1909": "smith", "conver1760": "conver"}


def load(path):
    with open(path) as f:
        return json.load(f)


def position_key(card_id: str) -> str:
    """v4 card ids (smith-17 / conver-08) → structure position keys (major-17)."""
    return f"major-{int(card_id.split('-')[1]):02d}"


def one_line(text: str, n: int = 140) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


# Appendix B symbols missing from the v4 vocabulary (Smith 1909). Axes: −3..3, negative = first pole
# (active, beginning, giving, inward, gain, willing, certain, singular). bbox null → no exemplar crop yet.
APPENDIX_B_SMITH = [
    ("path", "Path or road", "a track, road or river-way leading into the distance", ["setting"], [-1.0, -1.5, 0.0, 1.5, 0.0, -0.5, 0.5, -1.0],
     "a way forward: departure, the journey ahead", "major-18", [("major-18", 0.5), ("major-14", 0.4)], "the Moon: 'the path… between the two towers' (Waite 1911)"),
    ("wall", "Wall", "a masonry wall closing off part of the scene", ["setting"], [1.0, 0.5, 1.5, -1.0, 0.0, 1.0, -0.5, 0.0],
     "enclosure, protection, limit", "major-19", [("major-19", 0.5)], "the Sun: the child rides 'beyond a wall' (Waite 1911)"),
    ("gate_threshold", "Gate or threshold", "a doorway, gate or passage between two pillars or towers", ["setting"], [-0.5, -2.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0],
     "passage, initiation, the point of crossing", "major-18", [("major-18", 0.4), ("major-13", 0.3)], "the Moon: towers flanking the way; Death: the gate of the rising sun (Waite 1911)"),
    ("bridge", "Bridge", "a bridge spanning water", ["setting"], [-0.5, 0.0, -0.5, 1.5, -0.5, -0.5, 0.0, 0.0],
     "crossing, connection between two states", None, [], "Five of Cups: 'a bridge leading to a small keep' (Waite 1911)"),
    ("rose", "Rose", "a rose flower, often white or red", ["vegetation"], [-0.5, -1.0, -1.5, 0.0, -1.0, -0.5, -0.5, -0.5],
     "desire, passion, purity (white rose)", "major-00", [("major-00", 0.25), ("major-01", 0.2), ("major-13", 0.5)], "the Fool's white rose; the Magician's roses; Death's banner (Waite 1911)"),
    ("lily", "Lily", "a lily flower", ["vegetation"], [0.5, 0.0, -1.0, -1.0, -0.5, -0.5, -1.0, 0.0],
     "purity of thought, innocence", "major-01", [("major-01", 0.3)], "the Magician: 'roses and lilies' (Waite 1911)"),
    ("key", "Key", "one or two keys, often crossed", ["object"], [0.0, -0.5, 0.0, -1.0, -1.0, 0.0, -1.5, 0.0],
     "access, hidden knowledge unlocked, authority", "major-05", [("major-05", 0.4)], "the Hierophant: 'the crossed keys' (Waite 1911)"),
    ("ship", "Ship", "a sailing vessel on water", ["object"], [-1.5, -1.0, 0.0, 2.0, -0.5, -1.0, 0.5, 0.0],
     "voyage, trade, movement away", None, [], "Two and Three of Wands; Six of Swords (Waite 1911)"),
    ("garden", "Garden", "cultivated plants, wheat or a walled garden", ["vegetation"], [0.5, 0.5, -1.5, -0.5, -1.5, -0.5, -1.0, 0.5],
     "fruitfulness, abundance, cultivated growth", "major-03", [("major-03", 0.4)], "the Empress: 'a field of corn is ripening' (Waite 1911)"),
    ("elder", "Elder", "an aged figure with white or grey hair or beard", ["figure"], [1.5, 1.5, 0.0, -1.5, 0.0, 0.0, -1.5, -1.5],
     "age, accumulated knowledge, authority of time", "major-09", [("major-09", 0.8), ("major-05", 0.5), ("major-04", 0.5)], "the Hermit; the Hierophant; the Emperor (Waite 1911)"),
    ("rider", "Rider", "a figure mounted on a horse", ["figure"], [-2.0, -0.5, 0.0, 1.5, 0.0, -1.0, -0.5, -1.5],
     "arrival, force in motion, message", "major-13", [("major-13", 0.6), ("major-19", 0.5)], "Death 'rides a horse'; the Sun's child rider; the four Knights (Waite 1911)"),
    ("falling_figure", "Falling figure", "a human figure falling headlong", ["posture"], [1.0, 2.0, 0.5, 1.0, 2.0, 2.5, 2.0, 0.0],
     "sudden loss of position, catastrophe", "major-16", [("major-16", 0.8)], "the Tower: 'two figures falling' (Waite 1911)"),
    ("blindfold", "Blindfold", "a figure whose eyes are bound", ["posture"], [1.5, 0.0, 0.5, -1.5, 0.5, 2.0, 2.5, -1.0],
     "not seeing, refusal or inability to look", None, [], "Two of Swords; Eight of Swords (Waite 1911)"),
    ("bandage", "Bandage or binding", "cloth binding a figure's body", ["posture"], [2.0, 0.5, 1.0, -1.0, 1.0, 2.5, 1.5, -1.0],
     "restriction, being held", None, [], "Eight of Swords: 'a woman, bound and hoodwinked' (Waite 1911)"),
    ("hourglass", "Hourglass", "a sand timer", ["object"], [0.5, 1.5, 0.0, -0.5, 0.5, 1.0, 0.0, 0.0],
     "measured time, waiting", None, [], "rare in Smith 1909 — no exemplar; the Hermit carries a lantern, not an hourglass"),
    ("pentacle", "Pentacle", "a disc or coin bearing a five-pointed star", ["object"], [0.5, 0.0, 0.0, 0.0, -2.0, 0.0, -1.0, 0.0],
     "material value, the tangible, earned reward", "major-01", [("major-01", 0.3)], "the Magician's table: 'the four elements… pentacle' (Waite 1911); the whole suit of Pentacles"),
    ("throne", "Throne", "a seat of authority, often stone", ["object"], [1.0, 0.0, 0.5, -0.5, 0.0, 0.5, -2.0, -1.0],
     "established authority, stability", "major-04", [("major-04", 0.7), ("major-03", 0.5), ("major-05", 0.5), ("major-11", 0.5), ("major-02", 0.4)], "the Emperor 'seated on a throne' (Waite 1911)"),
    ("serpent", "Serpent", "a snake", ["animal"], [-0.5, 0.0, 0.5, 0.0, 0.5, 0.5, 1.0, -1.0],
     "knowledge, temptation, cyclic renewal", "major-06", [("major-06", 0.3), ("major-10", 0.3)], "the Lovers: 'the serpent… about the tree' (Waite 1911); the Wheel's Typhon"),
    ("cross", "Cross", "a cross emblem on clothing, a banner or a sceptre", ["object"], [0.0, 0.0, -0.5, -1.0, 0.0, 0.5, -1.5, 0.5],
     "faith, doctrine, sacrifice", "major-05", [("major-05", 0.4), ("major-20", 0.5), ("major-02", 0.4)], "the Hierophant's triple cross; Judgement's banner; the High Priestess's solar cross (Waite 1911)"),
    ("rain", "Rain", "falling rain or a downpour", ["water"], [1.0, 1.0, 0.5, -0.5, 1.5, 1.5, 1.0, 0.0],
     "sorrow, cleansing by loss", None, [], "Three of Swords: 'rain falling' (Waite 1911)"),
    ("sunrise_sunset", "Sunrise or sunset", "the sun at the horizon", ["celestial"], [0.0, -1.5, -0.5, 0.5, -1.0, -0.5, -0.5, 0.0],
     "transition of a cycle: a new day or a day ending", "major-13", [("major-13", 0.3), ("major-14", 0.3)], "Death: 'the sun of immortality' rising between the towers; Temperance's path to the crowned sun (Waite 1911)"),
]


def build(slug: str) -> dict:
    lib_dir = os.path.join(DATA, "libraries", slug)
    sheet = load(os.path.join(lib_dir, "elements.json"))
    prefix = LIBS[slug]
    tags = load(os.path.join(DATA, "card_elements.json"))
    leaves = [e for e in sheet if e.get("size_class")]
    keys = {e["id"] for e in leaves}
    symbols = []
    for e in leaves:
        att = e.get("attestations") or []
        src_pk = position_key(e["source_card"]) if e.get("source_card") else None
        symbols.append({
            "key": e["id"], "name": e["label"], "gloss": e.get("gloss", ""), "tags": [e["parent_id"]] if e.get("parent_id") else [],
            "declared_axes": [float(x) for x in e["historical_prior"]],
            "declared_text": one_line(att[0]["note"]) if att else one_line(e.get("gloss", "")),
            "exemplar": {"image_url": e.get("image_url"), "origin": "base_crop", "source_ref": {"position_key": src_pk, "bbox": e.get("bbox")}},
            "placement": "center" if e.get("size_class") == "large" else "any",
            "origin": "inherited_base", "inherited_from": {"base_deck_slug": slug, "symbol_key": e["id"]},
            "attestations": [{"source": a.get("source", ""), "note": a.get("note", ""), "base_card": position_key(a["card_id"]) if a.get("card_id") else None} for a in att],
            "prior_axes": [float(x) for x in e["historical_prior"]], "prior_source": "attestation", "status": "active",
            "size_class": e.get("size_class"),
        })
    by_card: dict[str, list] = {}
    for t in tags:
        if not t["card_id"].startswith(prefix + "-"):
            continue
        key = t["element_id"]
        if key not in keys and ("m_" + key) in keys:
            key = "m_" + key
        if key not in keys:
            continue
        by_card.setdefault(position_key(t["card_id"]), []).append({"key": key, "salience": float(t["visual_salience"])})
    if slug == "smith1909":
        for key, name, gloss, tg, axes, text, src, uses, att in APPENDIX_B_SMITH:
            if key in keys:
                continue
            symbols.append({
                "key": key, "name": name, "gloss": gloss, "tags": tg, "declared_axes": axes, "declared_text": text,
                "exemplar": {"image_url": None, "origin": "base_crop", "source_ref": {"position_key": src, "bbox": None}} if src else None,
                "placement": "any", "origin": "inherited_base", "inherited_from": {"base_deck_slug": slug, "symbol_key": key},
                "attestations": [{"source": "Waite 1911", "note": att, "base_card": src}], "prior_axes": axes, "prior_source": "attestation",
                "status": "active", "size_class": "small",
            })
            for pk, sal in uses:
                by_card.setdefault(pk, []).append({"key": key, "salience": sal})
    for pk in by_card:
        by_card[pk].sort(key=lambda x: -x["salience"])
    return {"slug": slug, "version": 1, "symbols": symbols, "symbols_by_card": dict(sorted(by_card.items()))}


if __name__ == "__main__":
    for slug in LIBS:
        reg = build(slug)
        os.makedirs(os.path.join(OUT, slug), exist_ok=True)
        with open(os.path.join(OUT, slug, "registry.json"), "w") as f:
            json.dump(reg, f, indent=1, ensure_ascii=False)
        with_ex = sum(1 for s in reg["symbols"] if s.get("exemplar") and s["exemplar"].get("image_url"))
        print(f"{slug:12s} symbols={len(reg['symbols'])} with_exemplar_image={with_ex} cards_mapped={len(reg['symbols_by_card'])}")

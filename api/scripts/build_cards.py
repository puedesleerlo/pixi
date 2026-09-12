"""Build data/cards.json from data/_sources/commons_verified.json (fetched from the Commons API).

Run:  api/.venv/bin/python api/scripts/build_cards.py
"""
from __future__ import annotations
import json, re, sys, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "_sources" / "commons_verified.json"
OUT = ROOT / "data" / "cards.json"

# number -> (English name, Smith commons stem, Conver commons stem, French title)
# Smith numbering: 08 Strength, 11 Justice.  Conver numbering: VIII La Justice, XI La Force.
SMITH = {
    0: ("The Fool", "RWS Tarot 00 Fool"), 1: ("The Magician", "RWS Tarot 01 Magician"),
    2: ("The High Priestess", "RWS Tarot 02 High Priestess"), 3: ("The Empress", "RWS Tarot 03 Empress"),
    4: ("The Emperor", "RWS Tarot 04 Emperor"), 5: ("The Hierophant", "RWS Tarot 05 Hierophant"),
    6: ("The Lovers", "RWS Tarot 06 Lovers"), 7: ("The Chariot", "RWS Tarot 07 Chariot"),
    8: ("Strength", "RWS Tarot 08 Strength"), 9: ("The Hermit", "RWS Tarot 09 Hermit"),
    10: ("Wheel of Fortune", "RWS Tarot 10 Wheel of Fortune"), 11: ("Justice", "RWS Tarot 11 Justice"),
    12: ("The Hanged Man", "RWS Tarot 12 Hanged Man"), 13: ("Death", "RWS Tarot 13 Death"),
    14: ("Temperance", "RWS Tarot 14 Temperance"), 15: ("The Devil", "RWS Tarot 15 Devil"),
    16: ("The Tower", "RWS Tarot 16 Tower"), 17: ("The Star", "RWS Tarot 17 Star"),
    18: ("The Moon", "RWS Tarot 18 Moon"), 19: ("The Sun", "RWS Tarot 19 Sun"),
    20: ("Judgement", "RWS Tarot 20 Judgement"), 21: ("The World", "RWS Tarot 21 World"),
}
CONVER = {
    0: ("Le Mat", "The Fool", "LE MAT"), 1: ("Le Bateleur", "The Magician", "I LE BATELEUR"),
    2: ("La Papesse", "The High Priestess", "II LA PAPESSE"), 3: ("L'Impératrice", "The Empress", "II L'IMPÉRATRICE"),
    4: ("L'Empereur", "The Emperor", "IIII-L'EMPEREUR"), 5: ("Le Pape", "The Hierophant", "V LE PAPE"),
    6: ("L'Amoureux", "The Lovers", "VI L'AMOUREUX"), 7: ("Le Chariot", "The Chariot", "VII LE CHARIOT"),
    8: ("La Justice", "Justice", "VIII LA JUSTICE"), 9: ("L'Hermite", "The Hermit", "VIIII L'HERMITE"),
    10: ("La Roue de Fortune", "Wheel of Fortune", "X LA ROUE DE FORTUNE"), 11: ("La Force", "Strength", "XI LA FORCE"),
    12: ("Le Pendu", "The Hanged Man", "XII LE PENDU"), 13: ("XIII (unnamed)", "Death", "13 XIII"),
    14: ("Tempérance", "Temperance", "XIIII TEMPERANCE"), 15: ("Le Diable", "The Devil", "XV LE DIABLE"),
    16: ("La Maison Dieu", "The Tower", "XVI LA MAISON DE DIEU"), 17: ("L'Étoile", "The Star", "XVII L'ETOILE"),
    18: ("La Lune", "The Moon", "XVIII LA LUNE"), 19: ("Le Soleil", "The Sun", "XVIIII LE SOLEIL"),
    20: ("Le Jugement", "Judgement", "XX LE JUGEMENT"), 21: ("Le Monde", "The World", "XXI LE MONDE"),
}


def clean_url(u: str) -> str:
    return u.split("?", 1)[0]


def thumb_url(full: str, width: int = 600) -> str:
    """Standard Commons thumbnail path for a JPEG: .../commons/a/ab/Name.jpg -> .../commons/thumb/a/ab/Name.jpg/600px-Name.jpg"""
    full = clean_url(full)
    m = re.match(r"^(https://upload\.wikimedia\.org/wikipedia/commons)/([0-9a-f])/([0-9a-f]{2})/(.+)$", full)
    if not m:
        return full
    base, h1, h2, name = m.groups()
    return f"{base}/thumb/{h1}/{h2}/{name}/{width}px-{name}"


def main() -> None:
    src = json.loads(SRC.read_text())
    by_name = {}  # english name -> (smith_id, conver_id)
    cards = []
    for n, (title, stem) in SMITH.items():
        key = f"File:{stem}.jpg"
        meta = src[key]
        cid = f"smith-{n:02d}"
        by_name.setdefault(title, {})["smith"] = cid
        cards.append({
            "id": cid, "title": title, "arcana": "major", "number": n,
            "image_url": clean_url(meta["url"]), "thumb_url": thumb_url(meta["url"]),
            "source_deck": "Smith 1909", "source_year": 1909,
            "rights_note": f"Public domain (Pamela Colman Smith, 1909 line art, London). Wikimedia Commons: {key} (licence tag: {meta.get('license')}).",
            "caption": "Pamela Colman Smith, 1909 · public domain",
            "commons_title": key, "sibling_ids": [],
        })
    for n, (fr, en, stem) in CONVER.items():
        key = f"File:{stem} Nicolas Conver Tarot 1760.jpg"
        meta = src[key]
        cid = f"conver-{n:02d}"
        by_name.setdefault(en, {})["conver"] = cid
        cards.append({
            "id": cid, "title": f"{fr} ({en})", "arcana": "major", "number": n,
            "image_url": clean_url(meta["url"]), "thumb_url": thumb_url(meta["url"]),
            "source_deck": "Conver 1760", "source_year": 1760,
            "rights_note": f"Public-domain artwork (Nicolas Conver, Marseille, 1760). Scan uploaded to Wikimedia Commons by 'Tarot World Project' under {meta.get('license')}; attribution kept. Wikimedia Commons: {key}.",
            "caption": "Nicolas Conver, Marseille, 1760 · public-domain artwork · scan CC BY-SA 4.0 via Wikimedia Commons",
            "commons_title": key, "sibling_ids": [],
        })
    ids = {c["id"]: c for c in cards}
    for en, pair in by_name.items():
        assert set(pair) == {"smith", "conver"}, (en, pair)
        ids[pair["smith"]]["sibling_ids"] = [pair["conver"]]
        ids[pair["conver"]]["sibling_ids"] = [pair["smith"]]
    assert len(cards) == 44
    text = json.dumps(cards, indent=1, ensure_ascii=False) + "\n"
    assert "Rider-Waite" not in text and "Rider–Waite" not in text
    OUT.write_text(text)
    print(f"wrote {OUT} ({len(cards)} cards)")


if __name__ == "__main__":
    main()

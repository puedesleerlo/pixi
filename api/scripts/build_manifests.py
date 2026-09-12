"""Build data/base_decks/<slug>/manifest.json for the catalog (spec v5 §9).

Cards are only listed when their Commons files were resolved by verify_commons.py
(data/_sources/*.json) or by the v4 corpus build (data/cards.json). Never guess a URL.
Trademark rule: the trademarked deck name is never written; say "Smith 1909".
"""
from __future__ import annotations

import json
import os
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "base_decks")
TODAY = date.today().isoformat()
REVIEWER = "datos@corlide.org (automated Commons imageinfo check, build_manifests.py)"

RANKS = ["Ace", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Page", "Knight", "Queen", "King"]
SUITS = {"Wands": "wands", "Cups": "cups", "Swords": "swords", "Pents": "pentacles"}
SUIT_NAMES = {"Wands": "Wands", "Cups": "Cups", "Swords": "Swords", "Pents": "Pentacles"}


def load(path):
    with open(path) as f:
        return json.load(f)


def write(slug: str, manifest: dict) -> None:
    os.makedirs(os.path.join(OUT, slug), exist_ok=True)
    manifest["card_count"] = len(manifest["cards"])
    with open(os.path.join(OUT, slug, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    print(f"{slug:16s} {manifest['status']:8s} cards={len(manifest['cards'])}")


def smith() -> dict:
    cards_v4 = [c for c in load(os.path.join(DATA, "cards.json")) if c["id"].startswith("smith-")]
    minors = load(os.path.join(DATA, "_sources", "commons_smith_minors.json"))
    cards = []
    for c in sorted(cards_v4, key=lambda c: c["number"]):
        cards.append({"position_key": f"major-{c['number']:02d}", "title": c["title"], "image_url": c["image_url"],
                      "thumb_url": c["thumb_url"], "caption": "Pamela Colman Smith, 1909 · public domain",
                      "commons_title": c["commons_title"], "license": "Public domain"})
    missing = []
    for suit, skey in SUITS.items():
        for n in range(1, 15):
            t = f"File:{suit}{n:02d}.jpg"
            v = minors.get(t)
            if not v or v.get("missing"):
                missing.append(t)
                continue
            cards.append({"position_key": f"{skey}-{n:02d}", "title": f"{RANKS[n - 1]} of {SUIT_NAMES[suit]}", "image_url": v["url"],
                          "thumb_url": v.get("thumb") or v["url"], "caption": "Pamela Colman Smith, 1909 · public domain",
                          "commons_title": t, "license": v.get("license") or "Public domain"})
    status = "ready" if len(cards) == 78 and not missing else "partial"
    return {
        "slug": "smith1909", "name": "Smith 1909", "tradition": "Waite–Smith line art (English occult tarot)", "year": 1909,
        "origin": "London, Rider & Son; drawn by Pamela Colman Smith under A. E. Waite's direction",
        "rights_note": "Public domain: first published 1909–1910 in the United Kingdom and United States, before 1929. "
                       "Scans from Wikimedia Commons, public domain. Not the 1971 recolored edition (copyrighted). "
                       "The trademarked deck name is not used anywhere in this project; say 'Smith 1909'.",
        "source_urls": ["https://commons.wikimedia.org/wiki/File:RWS_Tarot_00_Fool.jpg", "https://commons.wikimedia.org/wiki/File:Cups01.jpg"],
        "structure_template": "tarot78", "attestation_sources": ["Waite, A. E. (1911). The Pictorial Key to the Tarot. (Wikisource, public domain)"],
        "status": status, "missing": missing,
        "rights_checklist": {"source_page": "https://commons.wikimedia.org/wiki/File:RWS_Tarot_00_Fool.jpg",
                             "license_text": "Public domain — published before 1929 (Commons template PD-US); artist Pamela Colman Smith (d. 1951)",
                             "date": TODAY, "reviewer": REVIEWER},
        "cards": cards,
    }


def conver() -> dict:
    cards_v4 = [c for c in load(os.path.join(DATA, "cards.json")) if c["id"].startswith("conver-")]
    extra = load(os.path.join(DATA, "_sources", "commons_conver_extra.json"))
    cards = []
    for c in sorted(cards_v4, key=lambda c: c["number"]):
        cards.append({"position_key": f"major-{c['number']:02d}", "title": c["title"], "image_url": c["image_url"],
                      "thumb_url": c["thumb_url"], "caption": c["caption"], "commons_title": c["commons_title"],
                      "license": "Public-domain artwork · scan CC BY-SA 4.0 (Wikimedia Commons uploader)"})
    aces = {"File:As BATON Nicolas Conver Tarot 1760.jpg": ("wands-01", "As de Bâton (Ace of Wands)"),
            "File:As ÉPÉE Nicolas Conver Tarot 1760.jpg": ("swords-01", "As d'Épée (Ace of Swords)")}
    for t, (pk, title) in aces.items():
        v = extra.get(t)
        if v and not v.get("missing"):
            cards.append({"position_key": pk, "title": title, "image_url": v["url"], "thumb_url": v.get("thumb") or v["url"],
                          "caption": "Nicolas Conver, Marseille, 1760 · public-domain artwork · scan CC BY-SA 4.0 via Wikimedia Commons",
                          "commons_title": t, "license": v.get("license")})
    return {
        "slug": "conver1760", "name": "Tarot de Marseille — Conver 1760", "tradition": "Tarot de Marseille (type II)", "year": 1760,
        "origin": "Marseille, Nicolas Conver (master card-maker); the woodblocks were later reused by Camoin",
        "rights_note": "Public-domain artwork (1760). The Wikimedia Commons scans are credited CC BY-SA 4.0 by their uploader; "
                       "captions credit the scan. Only the 22 trumps and two aces are verified on Commons so far; the rest of "
                       "the 78 must be added from BnF Gallica (btv1b10520316w) with a page map.",
        "source_urls": ["https://commons.wikimedia.org/wiki/File:LE_MAT_Nicolas_Conver_Tarot_1760.jpg",
                        "https://gallica.bnf.fr/ark:/12148/btv1b10520316w"],
        "structure_template": "tarot78",
        "attestation_sources": ["Marseille tradition (standard readings)", "Court de Gébelin (1781), Le Monde primitif, vol. VIII"],
        "status": "partial", "missing": ["minors except the two aces"],
        "rights_checklist": {"source_page": "https://commons.wikimedia.org/wiki/File:LE_MAT_Nicolas_Conver_Tarot_1760.jpg",
                             "license_text": "Artwork public domain (1760); scans CC BY-SA 4.0 by the Commons uploader", "date": TODAY, "reviewer": REVIEWER},
        "cards": cards,
    }


PLANNED = [
    ("noblet1650", "Tarot de Marseille — Noblet", "Tarot de Marseille (type I)", 1650, "Paris, Jean Noblet; some cards restored",
     "Public domain (c. 1650). BnF Gallica scans; restoration status per card must be noted.", ["https://gallica.bnf.fr/ark:/12148/btv1b10537361s"], "tarot78",
     ["Marseille tradition (standard readings)"]),
    ("solabusca1491", "Sola Busca", "Italian Renaissance engraved tarocchi", 1491, "Ferrara or Venice; engraved, hand-coloured",
     "Public domain (1491). Scans via Wikimedia Commons / Pinacoteca di Brera.", ["https://commons.wikimedia.org/wiki/Category:Sola_Busca_tarot"], "tarot78",
     ["Sola Busca scholarship (Brera exhibition catalogue, 2012)"]),
    ("visconti-sforza", "Visconti-Sforza (Morgan–Bergamo)", "Italian Renaissance hand-painted tarocchi", 1450, "Milan, workshop of Bonifacio Bembo; 74 cards survive",
     "Public domain (c. 1450). Scans via the Morgan Library and Wikimedia Commons.", ["https://www.themorgan.org/collection/tarot-cards", "https://commons.wikimedia.org/wiki/Category:Visconti-Sforza_tarot_deck"], "tarot78",
     ["Morgan Library catalogue notes"]),
    ("etteilla1789", "Grand Etteilla", "French cartomantic tarot", 1789, "Paris, Jean-Baptiste Alliette (Etteilla)",
     "Public domain (1789). BnF Gallica / Wikimedia Commons scans.", ["https://commons.wikimedia.org/wiki/Category:Grand_Etteilla"], "tarot78",
     ["Etteilla (1789), Manière de se récréer avec le jeu de cartes nommées tarots"]),
    ("mantegna1465", "Tarocchi del Mantegna", "Italian Renaissance engravings (E-series)", 1465, "Ferrara; not by Mantegna; 50 prints in five groups of ten",
     "Public domain (c. 1465). Wikimedia Commons scans.", ["https://commons.wikimedia.org/wiki/Category:Tarocchi_del_Mantegna"], "mantegna50",
     ["Hind, A. M. (1938). Early Italian Engraving"]),
    ("lenormand1846", "Petit Lenormand (Game of Hope)", "German/French fortune-telling cards", 1846, "Based on J. K. Hechtel's Das Spiel der Hoffnung (1799)",
     "Public domain (1846 and earlier). Wikimedia Commons scans.", ["https://commons.wikimedia.org/wiki/Category:Petit_Lenormand"], "lenormand36",
     ["Lenormand tradition (standard card meanings)"]),
    ("minchiate", "Minchiate Fiorentine", "Florentine 97-card tarocchi", 1750, "Florence, 18th century printings",
     "Public domain (18th century). Wikimedia Commons / BnF scans; partial sets.", ["https://commons.wikimedia.org/wiki/Category:Minchiate"], "free",
     ["Minchiate scholarship (Pratesi)"]),
    ("aiga-dot", "AIGA / DOT Symbol Signs (non-tarot)", "Wayfinding pictograms", 1974, "AIGA for the U.S. Department of Transportation, 1974–1979",
     "Public domain (U.S. government work). Vector files from aiga.org.", ["https://www.aiga.org/resources/symbol-signs"], "free",
     ["ISO 7001 / DOT symbol sign notes"]),
    ("noto-emoji", "Noto Emoji subset (non-tarot)", "Emoji glyphs", 2014, "Google Noto Emoji; a curated subset of ~120 glyphs",
     "Apache 2.0 (image assets) / SIL OFL (font). GitHub googlefonts/noto-emoji.", ["https://github.com/googlefonts/noto-emoji"], "free",
     ["Unicode CLDR short names"]),
]


def planned(slug, name, tradition, year, origin, rights, urls, structure, sources) -> dict:
    return {"slug": slug, "name": name, "tradition": tradition, "year": year, "origin": origin, "rights_note": rights, "source_urls": urls,
            "structure_template": structure, "attestation_sources": sources, "status": "planned", "missing": ["all cards (not yet ingested)"],
            "rights_checklist": {"source_page": urls[0], "license_text": rights, "date": None, "reviewer": None}, "cards": []}


if __name__ == "__main__":
    write("smith1909", smith())
    write("conver1760", conver())
    for row in PLANNED:
        write(row[0], planned(*row))

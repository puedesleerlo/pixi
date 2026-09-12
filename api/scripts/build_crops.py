#!/usr/bin/env python
"""Cut rectangular crops for a base library from its public-domain source cards.

    api/.venv/bin/python api/scripts/build_crops.py --library smith1909

Reads data/libraries/<library>/elements.json, downloads each source card (data/cards.json image_url,
cached in data/_cache/images/), crops `bbox` ([x0,y0,x1,y1], normalised), pads to the slot aspect on
white (small 1:1, large 3:4), saves api/static/crops/<library>/<id>.png (max side 400 px) and writes
image_url back into the sheet. Elements with bbox null keep image_url null and origin "tile".
No masking, no recolouring: rectangular crops only ("own the seams").
"""
import argparse
import json
import os
import sys
import urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")
STATIC = os.path.join(ROOT, "api", "static", "crops")
CACHE = os.path.join(DATA, "_cache", "images")
UA = {"User-Agent": "pixie-hackcmu/0.1 (datos@corlide.org)"}
MAX_SIDE = 400
ASPECT = {"small": (1, 1), "large": (3, 4)}  # w:h


def fetch_card(card: dict) -> str:
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, card["id"] + ".jpg")
    if os.path.exists(path):
        return path
    for url in (card["thumb_url"].replace("/600px-", "/640px-"), card["image_url"]):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
                f.write(r.read())
            return path
        except Exception as e:  # try the next url
            print(f"  fetch failed {url}: {e}")
    raise RuntimeError(f"could not fetch {card['id']}")


def pad_to_aspect(im: Image.Image, aspect: tuple[int, int]) -> Image.Image:
    aw, ah = aspect
    w, h = im.size
    target_w = max(w, int(round(h * aw / ah)))
    target_h = max(h, int(round(w * ah / aw)))
    canvas = Image.new("RGB", (target_w, target_h), "white")
    canvas.paste(im, ((target_w - w) // 2, (target_h - h) // 2))
    return canvas


def build(library_id: str) -> None:
    sheet_path = os.path.join(DATA, "libraries", library_id, "elements.json")
    elements = json.load(open(sheet_path))
    cards = {c["id"]: c for c in json.load(open(os.path.join(DATA, "cards.json")))}
    out_dir = os.path.join(STATIC, library_id)
    os.makedirs(out_dir, exist_ok=True)
    n_cut = n_tile = 0
    for e in elements:
        if not e.get("size_class"):
            continue  # a group: never placed, never cropped
        bbox = e.get("bbox")
        if not bbox:
            e["image_url"] = None
            e["origin"] = e.get("origin") if e.get("origin") == "generated" else "tile"
            n_tile += 1
            continue
        card = cards[e["source_card"]]
        im = Image.open(fetch_card(card)).convert("RGB")
        W, H = im.size
        x0, y0, x1, y1 = bbox
        crop = im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
        crop = pad_to_aspect(crop, ASPECT[e["size_class"]])
        crop.thumbnail((MAX_SIDE, MAX_SIDE))
        # flat-colour prints: a 96-colour palette keeps the look and cuts each file to ~50 KB (cellular demo)
        crop = crop.quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        out = os.path.join(out_dir, e["id"] + ".png")
        crop.save(out, optimize=True)
        e["image_url"] = f"/static/crops/{library_id}/{e['id']}.png"
        e["origin"] = "cut"
        n_cut += 1
    json.dump(elements, open(sheet_path, "w"), indent=1, ensure_ascii=False)
    print(f"{library_id}: {n_cut} crops written to {out_dir}, {n_tile} tiles")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", default="smith1909")
    a = ap.parse_args()
    build(a.library)

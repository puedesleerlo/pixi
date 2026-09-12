"""Batch Gemini vision tagging pass over the 44-card corpus (spec §4: one pass, cached to JSON).

    GEMINI_API_KEY=... api/.venv/bin/python api/scripts/tag_with_gemini.py            # -> data/card_elements.gemini.json
    GEMINI_API_KEY=... api/.venv/bin/python api/scripts/tag_with_gemini.py --apply    # merge into data/card_elements.json

Per card: fetch the thumbnail, send it with the LEAF vocabulary to gemini-2.5-flash, ask for JSON
{"tags": [{"element_id", "visual_salience"}]} restricted to elements visibly present. Responses are
cached in data/_cache/gemini/<card_id>.json so re-runs cost nothing. Human corrections are edits
to card_elements.json (no correction UI). With --apply, human rows win where both exist.
"""
from __future__ import annotations
import argparse, base64, json, os, sys, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CACHE = DATA / "_cache" / "gemini"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
UA = "pixie-hackcmu/0.1 (datos@corlide.org)"

SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "element_id": {"type": "string"},
                    "visual_salience": {"type": "number"},
                },
                "required": ["element_id", "visual_salience"],
            },
        }
    },
    "required": ["tags"],
}


def prompt_for(card: dict, leaves: list[dict]) -> str:
    vocab = "\n".join(f"- {e['id']}: {e['label']} — {e['gloss']}" for e in leaves)
    return (
        "You are tagging a historical tarot card image for a visual-communication study. "
        "List ONLY the vocabulary elements that are visibly present in THIS image (do not infer from the card's name), "
        "each with visual_salience in 0..1 = the share of visual attention it takes (the dominant subject ~0.9, "
        "minor details ~0.2-0.3). Use 3 to 8 elements. Use ids exactly as given.\n\n"
        f"Card: {card['title']} ({card['source_deck']}).\n\nVocabulary:\n{vocab}"
    )


def call_gemini(key: str, image_bytes: bytes, mime: str, prompt: str) -> dict:
    body = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(image_bytes).decode()}},
        ]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": SCHEMA,
            "temperature": 0.2,
        },
    }
    delay = 2.0
    last: Exception | None = None
    for attempt in range(3):
        try:
            r = httpx.post(URL, params={"key": key}, json=body, timeout=60, headers={"User-Agent": UA})
            if r.status_code in (429, 500, 502, 503, 504):
                raise RuntimeError(f"{r.status_code}: {r.text[:200]}")
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"gemini failed after 3 attempts: {last}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="merge results into data/card_elements.json")
    ap.add_argument("--only", nargs="*", help="card ids to (re)tag")
    args = ap.parse_args()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("GEMINI_API_KEY not set; nothing to do (the repo ships human tags).", file=sys.stderr)
        return 2
    cards = json.loads((DATA / "cards.json").read_text())
    elements = json.loads((DATA / "elements.json").read_text())
    leaves = [e for e in elements if e["parent_id"] is not None]
    leaf_ids = {e["id"] for e in leaves}
    CACHE.mkdir(parents=True, exist_ok=True)

    out = []
    for card in cards:
        if args.only and card["id"] not in args.only:
            continue
        cpath = CACHE / f"{card['id']}.json"
        if cpath.exists():
            resp = json.loads(cpath.read_text())
        else:
            img = httpx.get(card["thumb_url"], timeout=60, headers={"User-Agent": UA}, follow_redirects=True)
            img.raise_for_status()
            mime = img.headers.get("content-type", "image/jpeg").split(";")[0]
            resp = call_gemini(key, img.content, mime, prompt_for(card, leaves))
            cpath.write_text(json.dumps(resp, indent=1))
            time.sleep(0.5)
        seen = set()
        for t in resp.get("tags", []):
            eid = t.get("element_id")
            if eid not in leaf_ids or eid in seen:
                continue
            seen.add(eid)
            sal = min(1.0, max(0.0, float(t.get("visual_salience", 0.5))))
            out.append({"card_id": card["id"], "element_id": eid, "visual_salience": round(sal, 2), "tagged_by": "gemini"})
        print(f"{card['id']}: {len(seen)} tags")
    (DATA / "card_elements.gemini.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote data/card_elements.gemini.json ({len(out)} tags)")

    if args.apply:
        human = json.loads((DATA / "card_elements.json").read_text())
        have = {(t["card_id"], t["element_id"]) for t in human}
        merged = human + [t for t in out if (t["card_id"], t["element_id"]) not in have]
        merged.sort(key=lambda t: (t["card_id"], -t["visual_salience"]))
        (DATA / "card_elements.json").write_text(json.dumps(merged, indent=1) + "\n")
        print(f"merged into data/card_elements.json ({len(merged)} tags; human rows kept where both exist)")
        print("now run: api/.venv/bin/python api/scripts/validate_data.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

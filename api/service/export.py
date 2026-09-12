"""Export (spec §5.11): ZIP with images, manifest.json, grammar.csv, readings.csv (anonymised); print-sheet PDF
(2.75 × 4.75 in cards, 9 per US-letter page at 300 dpi, crop marks). Runs as job kind `export`."""
from __future__ import annotations

import csv
import io
import json
import zipfile

from PIL import Image, ImageDraw

import jobs as J
from pixie import relay as R
from service import measure

DPI = 300
CARD_IN = (2.75, 4.75)
PAGE_IN = (8.5, 11.0)


def _fetch_image(storage, url: str | None) -> bytes | None:
    if not url:
        return None
    if url.startswith("/media/"):
        return storage.get(url[len("/media/"):].split("?")[0])
    if url.startswith("http"):
        try:
            import httpx

            r = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": "pixie/0.5 (https://github.com/puedesleerlo/pixi; datos@corlide.org)"})
            return r.content if r.status_code == 200 else None
        except Exception:
            return None
    return None


def ctx_allows_network() -> bool:
    import os

    return os.environ.get("PIXIE_EXPORT_FETCH", "1") != "0"


def build_zip(store, storage, deck: dict) -> bytes:
    buf = io.BytesIO()
    cards = [c for c in store.find("cards", deck_id=deck["id"]) if c.get("status") != "archived"]
    versions = {v["id"]: v for v in store.find("versions", deck_id=deck["id"])}
    symbols = {s["id"]: s for s in store.find("symbols", deck_id=deck["id"])}
    g = measure.grammar(store, deck["id"])
    manifest = {"deck": {k: deck.get(k) for k in ("id", "slug", "name", "description", "visibility", "structure_template_id", "origin", "style_guide", "settings")},
                "exported_at": R.iso(R.utcnow()), "cards": [], "symbols": [{k: s.get(k) for k in ("id", "key", "name", "gloss", "declared_axes", "placement", "origin", "prior_axes", "prior_source", "status")} for s in symbols.values()]}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for c in cards:
            v = versions.get(c.get("current_version_id") or "")
            entry = {"id": c["id"], "position_key": c.get("position_key"), "title": c.get("title"), "status": c.get("status"),
                     "statement": (c.get("intent") or {}).get("statement") if c.get("status") in ("landed", "closed") else None,
                     "versions": [{"id": x["id"], "v": x["v"], "op": (x.get("how") or {}).get("op") or (x.get("how") or {}).get("mode"),
                                   "symbols_detected": x.get("symbols_detected", []), "checks": x.get("checks")} for x in sorted((x for x in versions.values() if x["card_id"] == c["id"]), key=lambda x: int(x["v"]))]}
            if v is not None:
                entry["image_url"] = v.get("image_url")
                data = _fetch_image(storage, v.get("image_url")) if ctx_allows_network() else None
                if data:
                    name = f"images/{c.get('position_key') or c['id']}.png"
                    z.writestr(name, data)
                    entry["image"] = name
            manifest["cards"].append(entry)
        z.writestr("manifest.json", json.dumps(manifest, indent=1, ensure_ascii=False))
        gcsv = io.StringIO()
        w = csv.writer(gcsv)
        w.writerow(["symbol_id", "key", "name", "axis", "coef", "ci_low", "ci_high", "n_readings", "n_edits", "prior", "drift_from_prior"])
        for row in g["symbols"]:
            for i in range(8):
                w.writerow([row["symbol_id"], row["key"], row["name"], i, row["coef"][i] if row["coef"] else "", row["ci_low"][i] if row["ci_low"] else "",
                            row["ci_high"][i] if row["ci_high"] else "", row["n_readings"], row["n_edits"], (row["prior_axes"] or [""] * 8)[i], row["drift_from_prior"] if row["drift_from_prior"] is not None else ""])
        z.writestr("grammar.csv", gcsv.getvalue())
        rcsv = io.StringIO()
        w = csv.writer(rcsv)
        w.writerow(["reading_id", "card_id", "version_id", "reader", "synthetic", "created_at"] + [f"axis_{i}" for i in range(8)] + ["free_text"])
        readers: dict[str, int] = {}
        for r in sorted(store.find("readings", deck_id=deck["id"]), key=lambda r: r.get("created_at") or ""):
            rid = readers.setdefault(r.get("reader_id") or "?", len(readers) + 1)
            w.writerow([r["id"], r["card_id"], r["version_id"], f"reader-{rid}", int(bool(r.get("synthetic"))), r.get("created_at")] + list(r["axes"]) + [r.get("free_text") or ""])
        z.writestr("readings.csv", rcsv.getvalue())
        z.writestr("README.txt", f"PIXIE export of deck '{deck.get('name')}' ({deck.get('slug')}). Readings are anonymised. "
                                 "Every metric in grammar.csv is recomputable from readings.csv and manifest.json (see docs/SPEC-v5.md §8).\n")
    return buf.getvalue()


def build_print_pdf(store, storage, deck: dict) -> bytes:
    cw, ch = int(CARD_IN[0] * DPI), int(CARD_IN[1] * DPI)
    pw, ph = int(PAGE_IN[0] * DPI), int(PAGE_IN[1] * DPI)
    cols, rows = 3, 3
    gx = (pw - cols * cw) // 2
    gy = (ph - rows * ch) // 2
    cards = [c for c in store.find("cards", deck_id=deck["id"]) if c.get("status") != "archived" and c.get("current_version_id")]
    cards.sort(key=lambda c: c.get("position_key") or "")
    versions = {v["id"]: v for v in store.find("versions", deck_id=deck["id"])}
    pages: list[Image.Image] = []
    page, k = None, 0
    for c in cards:
        v = versions.get(c["current_version_id"])
        data = _fetch_image(storage, v.get("image_url") if v else None)
        if page is None:
            page = Image.new("RGB", (pw, ph), "white")
            d = ImageDraw.Draw(page)
        i, j = k % cols, (k // cols) % rows
        x, y = gx + i * cw, gy + j * ch
        if data:
            try:
                im = Image.open(io.BytesIO(data)).convert("RGB").resize((cw, ch))
                page.paste(im, (x, y))
            except Exception:
                d.rectangle([x, y, x + cw, y + ch], outline="black")
        else:
            d.rectangle([x, y, x + cw, y + ch], outline="black")
            d.text((x + 20, y + 20), f"{c.get('position_key')} — no image", fill="black")
        m = 18
        for (px, py) in ((x, y), (x + cw, y), (x, y + ch), (x + cw, y + ch)):  # crop marks
            d.line([px - m, py, px - 4, py], fill="black"); d.line([px + 4, py, px + m, py], fill="black")
            d.line([px, py - m, px, py - 4], fill="black"); d.line([px, py + 4, px, py + m], fill="black")
        k += 1
        if k % (cols * rows) == 0:
            pages.append(page)
            page = None
    if page is not None:
        pages.append(page)
    if not pages:
        pages = [Image.new("RGB", (pw, ph), "white")]
    out = io.BytesIO()
    pages[0].save(out, "PDF", resolution=DPI, save_all=True, append_images=pages[1:])
    return out.getvalue()


@J.register("export")
def run_export(ctx: J.JobContext):
    store, storage = ctx.store, ctx.services["storage"]
    deck = store.get("decks", ctx.payload["deck_id"])
    kind = ctx.payload.get("kind", "zip")
    ctx.progress(0.1, "collecting")
    if kind == "pdf":
        data, ext, ct = build_print_pdf(store, storage, deck), "pdf", "application/pdf"
    else:
        data, ext, ct = build_zip(store, storage, deck), "zip", "application/zip"
    ctx.progress(0.8, "storing")
    key = storage.put(f"exports/{deck['id']}/{ctx.job['id']}.{ext}", data, ct)
    return {"key": key, "url": storage.url(key, private=deck.get("visibility") == "private"), "bytes": len(data), "kind": kind}

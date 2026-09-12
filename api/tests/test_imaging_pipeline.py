"""Imaging tests (spec §6): prompts, local provider, fidelity metrics, detection, pipeline. No network.
Runs on the perceptual embedding so it is fast and deterministic on any machine."""
import glob
import io
import os
import sys

import numpy as np
import pytest
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.dirname(HERE)
sys.path.insert(0, API)
os.environ["PIXIE_IMAGE_EMBED"] = "perceptual"
os.environ["PIXIE_DETECT"] = "fallback"
os.environ["PIXIE_IMAGE_PROVIDER"] = "local"

from pixie.imaging import detect as D, fidelity as F, prompts as P, style as S  # noqa: E402
from pixie.imaging.pipeline import run_edit, run_generate, run_symbol, run_tag  # noqa: E402
from pixie.imaging.providers.base import ZONES, get_provider, load_image, region_to_box, zone  # noqa: E402
from pixie.imaging.providers.local import LocalCollageProvider  # noqa: E402

CROPS = sorted(glob.glob(os.path.join(API, "static", "crops", "smith1909", "*.png")))
pytestmark = pytest.mark.skipif(len(CROPS) < 12, reason="Smith crops not built")


def crop(name):
    return os.path.join(API, "static", "crops", "smith1909", f"{name}.png")


class MemCtx:
    def __init__(self):
        self.files = {}
        self.notes = []

    def storage_put(self, key, data, content_type="image/png"):
        self.files[key] = (data, content_type)
        return key

    def progress(self, f, note=""):
        self.notes.append((f, note))


STYLE = {"prompt_prefix": "black ink line art on cream paper", "palette": ["#f4efe6", "#141414"], "line": "flat",
         "border": {"style": "plain", "color": "#141414"}, "aspect": "2.75x4.75"}
BOTTOM = zone("bottom")


def make_card(seed=0, names=("nude_figure", "star", "water_falling")):
    ex = [{"symbol_id": n, "name": n, "path": crop(n), "placement": p} for n, p in zip(names, ("center", "top", "left"))]
    return LocalCollageProvider().generate("x", n=1, seed=seed, symbol_exemplars=ex, style_guide=STYLE).images[0]


# ----------------------------------------------------------------------------- prompts
def test_prompts_assemble_exactly():
    symbols = [{"name": "Star", "gloss": "an eight-pointed star", "placement": "top"}, {"name": "Falling water", "gloss": "water poured downward"}]
    got = P.assemble_generate(STYLE, "The Star", symbols, "a calm night")
    assert got == ("black ink line art on cream paper Position: The Star. Symbols: Star — an eight-pointed star at top; "
                   "Falling water — water poured downward. a calm night Single card, full bleed inside border, no text.")
    got = P.assemble_edit("add", {"name": "Crown", "gloss": "a golden crown"}, placement_or_region="top", how_text="softer lines")
    assert got == ("Edit the provided card. Change only: add Crown (a golden crown) at the top. Keep everything else identical: "
                   "composition, figures, colors, line style, border, framing. Same size and aspect. softer lines")
    assert P.assemble_edit("remove", {"name": "Crown"}).startswith("Edit the provided card. Change only: remove Crown; fill the area consistently with the surroundings.")
    assert "replace Crown with Wheel in the same place and scale" in P.assemble_edit("replace", {"name": "Crown"}, {"name": "Wheel"})
    assert "more prominent" in P.assemble_edit("emphasize", {"name": "Crown"})
    assert "move Crown to the top, keep its appearance" in P.assemble_edit("reposition", {"name": "Crown"}, placement_or_region="top")


def test_denylist_and_how_text():
    assert P.strip_denylist("in the Rider-Waite style, like RWS, by US Games") == "in the style, like, by"
    assert "Rider" not in P.assemble_generate(STYLE, None, [], "a Rider Waite crown")
    with pytest.raises(ValueError):
        P.validate_how_text("add a tower in the back", ["Crown"], ["Crown", "Tower", "Star"])
    assert P.validate_how_text("softer crown lines", ["Crown"], ["Crown", "Tower"]) == "softer crown lines"


# ----------------------------------------------------------------------------- local provider
def test_local_generate_places_exemplars_in_zones():
    png = make_card()
    im = load_image(png)
    assert im.size == (550, 950)
    a = np.asarray(im, dtype=np.float32)
    paper = np.array([244, 239, 230], dtype=np.float32)
    for placement in ("center", "top", "left"):
        x0, y0, x1, y1 = region_to_box(zone(placement), 550, 950)
        inner = a[y0 + 10:y1 - 10, x0 + 10:x1 - 10]
        assert np.abs(inner - paper).mean() > 15, placement  # something was drawn there
    x0, y0, x1, y1 = region_to_box(zone("bottom"), 550, 950)
    assert np.abs(a[y0 + 10:y1 - 10, x0 + 10:x1 - 10] - paper).mean() < 3  # empty zone stays paper


def test_local_add_edit_is_confined_and_faithful():
    p = LocalCollageProvider()
    ok = 0
    for i in range(10):
        base = make_card(seed=i, names=(CROPS[(i * 3) % len(CROPS)].split("/")[-1][:-4], "star", "cup"))
        cand = p.edit(base, "add", op="add", region=BOTTOM, exemplar={"path": crop("crown")}, seed=i).images[0]
        b, c = np.asarray(load_image(base)), np.asarray(load_image(cand))
        x0, y0, x1, y1 = region_to_box(BOTTOM, 550, 950)
        outside = np.ones(b.shape[:2], dtype=bool)
        outside[y0:y1, x0:x1] = False
        assert np.array_equal(b[outside], c[outside])  # byte-identical outside the region
        assert np.abs(b[y0:y1, x0:x1].astype(int) - c[y0:y1, x0:x1].astype(int)).mean() > 5  # something changed inside
        fid = F.fidelity(base, cand, BOTTOM)
        assert fid["ssim_out"] >= 0.99 and fid["containment"] >= 0.9
        ok += fid["fidelity"] >= 0.85
    assert ok >= 8, f"only {ok}/10 add edits reached fidelity 0.85"


def test_local_remove_and_replace():
    p = LocalCollageProvider()
    base = make_card(seed=3)
    with_crown = p.edit(base, "add", op="add", region=BOTTOM, exemplar={"path": crop("crown")}, seed=1).images[0]
    removed = p.edit(with_crown, "remove", op="remove", region=BOTTOM, seed=1).images[0]
    x0, y0, x1, y1 = region_to_box(BOTTOM, 550, 950)
    r = np.asarray(load_image(removed))[y0 + 12:y1 - 12, x0 + 12:x1 - 12].astype(np.float32)
    assert r.std() < 12  # flat fill, no exemplar signal left
    fid = F.fidelity(with_crown, removed, BOTTOM)
    assert fid["ssim_out"] >= 0.99 and fid["containment"] >= 0.9
    replaced = p.edit(with_crown, "replace", op="replace", region=BOTTOM, exemplar={"path": crop("crown")}, to_exemplar={"path": crop("wheel")}, seed=2).images[0]
    fid2 = F.fidelity(with_crown, replaced, BOTTOM)
    assert fid2["ssim_out"] >= 0.99 and fid2["containment"] >= 0.9


def test_whole_image_cosmetic_is_not_confined():
    p = LocalCollageProvider()
    base = make_card(seed=5)
    add = F.fidelity(base, p.edit(base, "a", op="add", region=BOTTOM, exemplar={"path": crop("crown")}, seed=1).images[0], BOTTOM)
    heavy = p.edit(base, "c", op="cosmetic", strength=6.0).images[0]
    fid = F.fidelity(base, heavy, BOTTOM)
    assert fid["containment"] < 0.5  # the change is everywhere, not in the region
    assert fid["fidelity"] < 0.85 and fid["fidelity"] < add["fidelity"]


def test_identical_images_score_one_and_heatmap_is_valid():
    base = make_card(seed=7)
    fid = F.fidelity(base, base, BOTTOM)
    assert fid["fidelity"] == 1.0 and fid["ssim_out"] == 1.0 and fid["containment"] == 1.0
    cand = LocalCollageProvider().edit(base, "a", op="add", region=BOTTOM, exemplar={"path": crop("sun")}, seed=1).images[0]
    heat = F.diff_heatmap(base, cand)
    im = Image.open(io.BytesIO(heat))
    assert im.format == "PNG" and im.size == (550, 950)
    assert F.image_embed_backend() == "perceptual" and F.image_embed(base).shape == (768,)


def test_style_centroid_and_score():
    a, b = make_card(seed=1), make_card(seed=2)
    c = S.style_centroid([a, b])
    assert c.shape == (768,) and abs(np.linalg.norm(c) - 1.0) < 1e-4
    assert S.style_score(a, c) > 0.8
    assert S.style_score(a, None) is None


# ----------------------------------------------------------------------------- detection
def test_detect_fallback_and_reconcile():
    det = D.detect_symbols(b"", [], declared=[{"symbol_id": "star", "placement": "top"}])
    assert det == [{"symbol_id": "star", "present": True, "salience": 0.7, "bbox": zone("top"), "tagged_by": "declared_only"}]
    rec = D.reconcile([{"symbol_id": "star", "placement": "top"}, {"symbol_id": "crown", "placement": "center"}],
                      [{"symbol_id": "star", "present": True, "salience": 0.9, "bbox": None, "tagged_by": "vision"},
                       {"symbol_id": "tower", "present": True, "salience": 0.4, "bbox": None, "tagged_by": "vision"}])
    by = {x["symbol_id"]: x for x in rec["symbols_detected"]}
    assert by["star"]["salience"] == 0.9 and by["star"]["tagged_by"] == "vision"
    assert by["crown"]["salience"] == 0.3 and by["crown"]["tagged_by"] == "declared_only"
    assert rec["symbols_missing"] == ["crown"] and rec["also_detected"] == ["tower"] and "tower" in by


# ----------------------------------------------------------------------------- pipeline
def test_pipeline_generate_edit_symbol_tag():
    ctx = MemCtx()
    symbols = [{"symbol_id": "nude_figure", "name": "Nude figure", "gloss": "a nude figure", "placement": "center", "exemplar_path": crop("nude_figure")},
               {"symbol_id": "star", "name": "Star", "gloss": "an eight-pointed star", "placement": "top", "exemplar_path": crop("star")}]
    registry = [{"symbol_id": s["symbol_id"], "name": s["name"], "gloss": s["gloss"]} for s in symbols] + [{"symbol_id": "crown", "name": "Crown", "gloss": "a crown"}]
    gen = run_generate({"style_guide": STYLE, "position_title": "The Star", "symbols": symbols, "prompt_user": "quiet night", "n": 2, "seed": 4,
                        "registry": registry, "storage_prefix": "t/gen"}, ctx)
    assert gen["provider"] == "local" and len(gen["candidates"]) == 2 and gen["prompt_full"].startswith("black ink")
    c0 = gen["candidates"][0]
    assert c0["image_key"] in ctx.files and c0["thumb_key"] in ctx.files and c0["width"] == 550
    assert {x["symbol_id"] for x in c0["symbols_detected"]} == {"nude_figure", "star"} and c0["symbols_missing"] == []
    assert c0["style_score"] is None  # no references given
    base = ctx.files[c0["image_key"]][0]

    with pytest.raises(ValueError):
        run_edit({"base_image": base, "op": "add", "symbol": {"symbol_id": "crown", "name": "Crown", "exemplar_path": crop("crown")},
                  "placement": "bottom", "how_text": "add a star too", "registry": registry, "storage_prefix": "t/edit"}, ctx)
    ed = run_edit({"base_image": base, "op": "add", "symbol": {"symbol_id": "crown", "name": "Crown", "gloss": "a crown", "exemplar_path": crop("crown")},
                   "placement": "bottom", "how_text": "soft edges", "n": 2, "seed": 9, "fidelity_threshold": 0.85, "registry": registry,
                   "declared": [{"symbol_id": s["symbol_id"], "placement": s["placement"]} for s in symbols], "style_refs": [base],
                   "storage_prefix": "t/edit"}, ctx)
    assert ed["counts_as_experiment"] is True and ed["op"] == "add" and ed["expected_region"] == zone("bottom")
    assert ed["prompt_full"].startswith("Edit the provided card. Change only: add Crown (a crown) at the bottom.")
    best = ed["candidates"][0]
    assert best["fidelity"] >= 0.85 and best["containment"] >= 0.9 and best["heatmap_key"] in ctx.files
    assert ed["retries"] == 0 and best["style_score"] is not None
    assert {x["symbol_id"] for x in best["symbols_detected"]} == {"nude_figure", "star", "crown"}
    assert {d["symbol_id"] for d in ed["declared_after"]} == {"nude_figure", "star", "crown"}

    cos = run_edit({"base_image": base, "op": "cosmetic", "how_text": "warmer light", "registry": registry, "storage_prefix": "t/cos"}, ctx)
    assert cos["counts_as_experiment"] is False and cos["expected_region"] is None and len(cos["candidates"]) == 1

    rem = run_edit({"base_image": ctx.files[best["image_key"]][0], "op": "remove", "symbol": {"symbol_id": "crown", "name": "Crown"}, "placement": "bottom",
                    "registry": registry, "declared": ed["declared_after"], "storage_prefix": "t/rem"}, ctx)
    assert {d["symbol_id"] for d in rem["declared_after"]} == {"nude_figure", "star"} and rem["candidates"][0]["fidelity"] >= 0.85

    sym = run_symbol({"name": "Crown", "gloss": "a crown", "exemplar_path": crop("crown"), "n": 1, "storage_prefix": "t/sym"}, ctx)
    assert sym["candidates"][0]["width"] == 400
    tag = run_tag({"image": base, "registry": registry, "declared": [{"symbol_id": "star", "placement": "top"}]})
    assert tag["symbols_detected"][0]["symbol_id"] == "star" and tag["backend"] == "declared_only"
    assert any(n for _, n in ctx.notes)


def test_provider_selection_defaults_to_local(monkeypatch):
    for k in ("GEMINI_API_KEY", "BFL_API_KEY", "OPENAI_API_KEY", "PIXIE_IMAGE_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    assert get_provider().name == "local"
    assert set(ZONES) == {"center", "top", "bottom", "left", "right", "any"}

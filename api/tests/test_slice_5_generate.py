"""Slice 5 — Generate menu: prompt / reference / upload modes, candidates with style score and detection,
choose → reading, quota 409. Local collage provider, perceptual embeddings, declared-only detection."""
import base64
import io
import os

import pytest

os.environ["PIXIE_IMAGE_PROVIDER"] = "local"
os.environ["PIXIE_IMAGE_EMBED"] = "perceptual"
os.environ["PIXIE_DETECT"] = "fallback"

from tests.v5util import login, make_client, seed_base  # noqa: E402


def png_bytes(color=(200, 30, 30), size=(160, 160), stripe=True) -> bytes:
    from PIL import Image, ImageDraw

    im = Image.new("RGB", size, color)
    d = ImageDraw.Draw(im)
    if stripe:
        d.rectangle([size[0] // 4, size[1] // 4, 3 * size[0] // 4, 3 * size[1] // 4], outline=(20, 20, 20), width=6)
        d.ellipse([size[0] // 3, size[1] // 3, 2 * size[0] // 3, 2 * size[1] // 3], fill=(240, 220, 90))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def card_png() -> bytes:
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (550, 950), (244, 239, 230))
    d = ImageDraw.Draw(im)
    d.rectangle([12, 12, 537, 937], outline=(20, 20, 20), width=4)
    d.ellipse([175, 300, 375, 500], fill=(210, 190, 120), outline=(20, 20, 20), width=3)
    d.line([60, 900, 490, 900], fill=(20, 20, 20), width=3)
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def localize_base(client, slug="smith1909"):
    """seed_base points base cards at example.org; give them real local images and give symbols exemplar crops."""
    from routers.deps import storage, store

    s, st = store(), storage()
    for bc in s.find("base_cards", base_deck_id=f"bd_{slug}"):
        key = st.put(f"base/{slug}/{bc['position_key']}.png", card_png(), "image/png")
        bc["image_url"] = st.url(key)
        s.put("base_cards", bc)
    colors = {"crown": (230, 200, 40), "sun": (250, 170, 30), "tower": (90, 90, 120)}
    for bs in s.find("base_symbols", base_deck_id=f"bd_{slug}"):
        key = st.put(f"base/{slug}/sym_{bs['key']}.png", png_bytes(colors.get(bs["key"], (120, 120, 120)), (120, 120)), "image/png")
        bs["exemplar"] = {"image_url": st.url(key), "origin": "base_crop", "source_card": None}
        s.put("base_symbols", bs)


def make_deck(client, h, name="Gen deck", quota=200, policy="any_member", threshold=3, card_mode="reference", visibility="public"):
    r = client.post("/api/decks", json={"name": name, "visibility": visibility, "origin": {"kind": "base", "base_deck_id": "bd_smith1909"},
                                        "import_symbols": ["crown", "sun", "tower"], "card_mode": card_mode,
                                        "settings": {"generation_quota_month": quota, "default_editor_policy": policy, "ready_threshold": threshold,
                                                     "candidates_per_generation": 2, "allow_guest_readers": True}}, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()


def symbols_of(client, did, h):
    r = client.get(f"/api/decks/{did}/symbols", headers=h)
    assert r.status_code == 200, r.text
    return {s["key"]: s for s in r.json()}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with make_client(tmp_path_factory.mktemp("s5")) as c:
        seed_base(c, n_cards=3)
        localize_base(c)
        yield c


@pytest.fixture(scope="module")
def ctx(client):
    maker = login(client, "maker5@example.org", "Maker")
    other = login(client, "other5@example.org", "Other")
    deck = make_deck(client, maker["h"])
    client.post(f"/api/decks/{deck['id']}/members", json={"user_id": other["user"]["id"], "role": "member"}, headers=maker["h"])
    return {"maker": maker, "other": other, "deck": deck, "syms": symbols_of(client, deck["id"], maker["h"])}


def test_reference_deck_has_empty_positions(client, ctx):
    tiles = client.get(f"/api/decks/{ctx['deck']['id']}/cards").json()
    assert tiles == []  # reference mode: positions empty, base cards available as references


def test_card_from_prompt(client, ctx):
    did, h, syms = ctx["deck"]["id"], ctx["maker"]["h"], ctx["syms"]
    r = client.post(f"/api/decks/{did}/cards", json={"position_key": "major-00", "intent": {"statement": "a first step into the unknown", "axes": [-3, -3, -1, 1, -1, -2, 2, -2]}}, headers=h)
    assert r.status_code == 201, r.text
    card = r.json()
    assert card["status"] == "draft" and card["position_key"] == "major-00" and card["title"] == "The Fool" and card["intent"]["statement"]
    assert card["can"]["generate"] and card["can"]["set_intent"] and not card["can"]["edit"]
    # position taken
    assert client.post(f"/api/decks/{did}/cards", json={"position_key": "major-00"}, headers=h).status_code == 409
    # unknown symbol → propose it first
    bad = client.post(f"/api/cards/{card['id']}/generate", json={"mode": "prompt", "prompt_user": "x", "symbols": ["sy_nope"]}, headers=h)
    assert bad.status_code == 422
    r = client.post(f"/api/cards/{card['id']}/generate", json={"mode": "prompt", "prompt_user": "a traveller at a cliff edge, Rider-Waite style",
                                                              "symbols": [syms["crown"]["id"], syms["sun"]["id"]], "n": 2}, headers=h)
    assert r.status_code == 202, r.text
    out = r.json()
    assert out["job"]["status"] == "done" and out["job"]["result"]["candidates"] == 2 and out["version_id"]
    view = client.get(f"/api/cards/{card['id']}", headers=h).json()
    pv = view["pending_version"]
    assert pv and pv["status"] == "candidates" and len(pv["how"]["candidates"]) == 2
    c0 = pv["how"]["candidates"][0]
    assert c0["image_url"].startswith("/media/") and c0["width"] == 550 and c0["height"] == 950
    assert "style_score" in c0 and c0["backend"] == "declared_only"
    assert {x["symbol_id"] for x in c0["symbols_detected"]} == {syms["crown"]["id"], syms["sun"]["id"]}
    assert all(x["tagged_by"] == "declared_only" for x in c0["symbols_detected"]) and isinstance(c0["symbols_missing"], list)
    assert "Rider-Waite" not in pv["how"]["prompt_full"] and "Position: The Fool." in pv["how"]["prompt_full"]
    assert client.get(c0["image_url"]).status_code == 200
    # only the creator picks
    assert client.post(f"/api/versions/{pv['id']}/choose", json={"index": 1}, headers=ctx["other"]["h"]).status_code == 403
    r = client.post(f"/api/versions/{pv['id']}/choose", json={"index": 1}, headers=h)
    assert r.status_code == 200, r.text
    chosen = r.json()
    assert chosen["version"]["how"]["chosen_index"] == 1 and chosen["version"]["image_url"].startswith("/media/")
    assert chosen["card"]["status"] == "reading" and chosen["card"]["current_version_id"] == pv["id"]
    assert chosen["card"]["current_version"]["checks"]["style_score"] is not None
    assert {x["symbol_id"] for x in chosen["card"]["current_version"]["symbols_detected"]} == {syms["crown"]["id"], syms["sun"]["id"]}
    assert any(x["declared_only"] for x in chosen["card"]["current_version"]["symbols_detected"])
    assert client.post(f"/api/versions/{pv['id']}/choose", json={"index": 0}, headers=h).status_code == 409  # already chosen
    tiles = client.get(f"/api/decks/{did}/cards").json()
    assert len(tiles) == 1 and tiles[0]["status"] == "reading" and tiles[0]["needs_readings"]
    ctx["card_prompt"] = card["id"]


def test_card_from_base_reference_and_intent_later(client, ctx):
    did, h, syms = ctx["deck"]["id"], ctx["maker"]["h"], ctx["syms"]
    card = client.post(f"/api/decks/{did}/cards", json={"position_key": "major-01"}, headers=h).json()
    r = client.post(f"/api/cards/{card['id']}/generate", json={"mode": "reference", "reference": {"base_card_id": "bc_smith1909_major-01"},
                                                              "symbols": [syms["tower"]["id"]], "n": 1, "strength": 0.5}, headers=h)
    assert r.status_code == 202, r.text
    pv = client.get(f"/api/cards/{card['id']}", headers=h).json()["pending_version"]
    assert pv["how"]["mode"] == "reference" and pv["how"]["reference_image_url"].startswith("/media/") and len(pv["how"]["candidates"]) == 1
    chosen = client.post(f"/api/versions/{pv['id']}/choose", json={"index": 0}, headers=h).json()
    assert chosen["card"]["status"] == "draft"  # no intent yet
    r = client.patch(f"/api/cards/{card['id']}", json={"intent": {"statement": "skill held in reserve", "axes": [-2, -2, -1, -1, -1, -1, -2, -2]}}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "reading"
    assert client.patch(f"/api/cards/{card['id']}", json={"title": "x"}, headers=ctx["other"]["h"]).status_code == 403


def test_upload_mode(client, ctx):
    did, h, syms = ctx["deck"]["id"], ctx["maker"]["h"], ctx["syms"]
    card = client.post(f"/api/decks/{did}/cards", json={"position_key": "major-02", "intent": {"statement": "what is kept behind the veil", "axes": [2, 0, 2, -3, 0, 0, 2, -2]}}, headers=h).json()
    b64 = base64.b64encode(card_png()).decode()
    assert client.post(f"/api/cards/{card['id']}/generate", json={"mode": "upload", "image_base64": b64, "symbols": [syms["crown"]["id"]]}, headers=h).status_code == 422  # rights
    r = client.post(f"/api/cards/{card['id']}/generate", json={"mode": "upload", "image_base64": b64, "rights_attested": True, "symbols": [syms["crown"]["id"]]}, headers=h)
    assert r.status_code == 202, r.text
    assert r.json()["job"] is None and r.json()["card"]["status"] == "reading"
    v = r.json()["card"]["current_version"]
    assert v["how"]["mode"] == "upload" and v["how"]["provider"] == "upload" and v["image_url"].startswith("/media/")
    ctx["card_upload"] = card["id"]


def test_quota_and_readers_view(client, ctx):
    h = ctx["maker"]["h"]
    small = make_deck(client, h, name="No quota", quota=0)
    syms = symbols_of(client, small["id"], h)
    card = client.post(f"/api/decks/{small['id']}/cards", json={"position_key": "major-00"}, headers=h).json()
    r = client.post(f"/api/cards/{card['id']}/generate", json={"mode": "prompt", "prompt_user": "x", "symbols": [syms["crown"]["id"]]}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "quota_exceeded"
    # a non-encoder sees no intent on a reading card; the maker does
    view = client.get(f"/api/cards/{ctx['card_prompt']}", headers=ctx["other"]["h"]).json()
    assert "intent" not in view and view["can"]["read"] and view["can"]["edit"] and view["pending_version"] is None  # any member may edit a card with an image
    mine = client.get(f"/api/cards/{ctx['card_prompt']}", headers=h).json()
    assert mine["intent"]["statement"] and mine["is_encoder"]

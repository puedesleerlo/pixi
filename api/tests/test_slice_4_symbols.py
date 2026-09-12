"""Slice 4: registry add/propose/approve/import/merge/retire/detail."""
import base64
import io

import pytest

from tests.v5util import login, make_client, seed_base


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with make_client(tmp_path_factory.mktemp("s4")) as c:
        seed_base(c, n_cards=2)
        yield c


@pytest.fixture(scope="module")
def ctx(client):
    cur = login(client, "cur@example.org", "Cur")
    mem = login(client, "mem@example.org", "Mem")
    d = client.post("/api/decks", json={"name": "Symbols deck", "visibility": "public", "origin": {"kind": "base", "base_deck_id": "bd_smith1909"}, "import_symbols": []}, headers=cur["h"]).json()
    client.post(f"/api/decks/{d['id']}/members", json={"user_id": mem["user"]["id"], "role": "member"}, headers=cur["h"])
    return {"cur": cur, "mem": mem, "deck": d}


def png_b64(color=(200, 30, 30)):
    from PIL import Image
    im = Image.new("RGB", (64, 64), color)
    b = io.BytesIO(); im.save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode()


def test_add_with_exemplar_upload(client, ctx):
    did = ctx["deck"]["id"]
    r = client.post(f"/api/decks/{did}/symbols", json={"name": "Downward water", "gloss": "water poured downward", "declared_axes": [0, 1, -2, 1, 0, 0, 0, 0],
                                                        "declared_text": "release", "placement": "bottom", "exemplar_upload": png_b64()}, headers=ctx["cur"]["h"])
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["key"] == "downward_water" and s["origin"] == "community" and s["status"] == "active" and s["measured"]["coherence"] == "untested"
    assert s["exemplar"]["origin"] == "upload" and s["exemplar"]["image_url"].startswith("/media/")
    assert client.get(s["exemplar"]["image_url"]).status_code == 200
    # duplicate names get unique keys; bad axes rejected
    assert client.post(f"/api/decks/{did}/symbols", json={"name": "Downward water", "declared_axes": [0] * 8}, headers=ctx["cur"]["h"]).json()["key"] == "downward_water_2"
    assert client.post(f"/api/decks/{did}/symbols", json={"name": "Bad", "declared_axes": [9] * 8}, headers=ctx["cur"]["h"]).status_code == 422


def test_propose_then_approve(client, ctx):
    did = ctx["deck"]["id"]
    draft = {"name": "Threshold", "gloss": "a gate or doorway", "declared_axes": [-1, -2, 0, 1, 0, -1, 1, 0], "placement": "center"}
    p = client.post(f"/api/decks/{did}/symbol-proposals", json={"symbol_draft": draft, "note": "the deck needs a doorway"}, headers=ctx["mem"]["h"]).json()
    assert p["status"] == "open" and p["proposed_by"] == ctx["mem"]["user"]["id"]
    # the curator got a notification; the member cannot decide
    assert client.get("/api/notifications", headers=ctx["cur"]["h"]).json()["unread"] >= 1
    assert client.patch(f"/api/symbol-proposals/{p['id']}", json={"action": "approve"}, headers=ctx["mem"]["h"]).status_code == 403
    r = client.patch(f"/api/symbol-proposals/{p['id']}", json={"action": "approve"}, headers=ctx["cur"]["h"]).json()
    assert r["status"] == "approved" and r["symbol_id"]
    s = client.get(f"/api/symbols/{r['symbol_id']}").json()
    assert s["name"] == "Threshold" and s["proposed_by"] == ctx["mem"]["user"]["id"] and s["approved_by"] == ctx["cur"]["user"]["id"] and s["status"] == "active"
    assert client.patch(f"/api/symbol-proposals/{p['id']}", json={"action": "decline"}, headers=ctx["cur"]["h"]).status_code == 409
    # decline path with a note
    p2 = client.post(f"/api/decks/{did}/symbol-proposals", json={"symbol_draft": {**draft, "name": "Portal"}, "note": ""}, headers=ctx["mem"]["h"]).json()
    r2 = client.patch(f"/api/symbol-proposals/{p2['id']}", json={"action": "decline", "decision_note": "same as threshold"}, headers=ctx["cur"]["h"]).json()
    assert r2["status"] == "declined" and r2["decision_note"] == "same as threshold"
    mine = client.get(f"/api/decks/{did}/symbol-proposals", headers=ctx["mem"]["h"]).json()
    assert {x["status"] for x in mine} == {"approved", "declined"}


def test_import_from_base(client, ctx):
    did = ctx["deck"]["id"]
    r = client.post(f"/api/decks/{did}/symbols/import", json={"base_deck_slug": "smith1909", "symbol_keys": ["crown", "sun"]}, headers=ctx["cur"]["h"]).json()
    assert [s["key"] for s in r] == ["crown", "sun"] and all(s["origin"] == "inherited_base" and s["prior_source"] == "attestation" for s in r)
    again = client.post(f"/api/decks/{did}/symbols/import", json={"base_deck_slug": "smith1909"}, headers=ctx["cur"]["h"]).json()
    assert [s["key"] for s in again] == ["tower"]  # already-present keys are skipped
    assert client.post(f"/api/decks/{did}/symbols/import", json={"base_deck_slug": "smith1909"}, headers=ctx["mem"]["h"]).status_code == 403


def test_patch_rename_keeps_key_and_crop_from_base_card(client, ctx):
    did = ctx["deck"]["id"]
    syms = {s["key"]: s for s in client.get(f"/api/decks/{did}/symbols").json()}
    crown = syms["crown"]
    r = client.patch(f"/api/symbols/{crown['id']}", json={"name": "Crown of state", "declared_text": "authority"}, headers=ctx["cur"]["h"]).json()
    assert r["key"] == "crown" and r["name"] == "Crown of state"
    # crop from a base card: stub the fetch with a local image
    from routers.deps import storage
    from PIL import Image
    import io as _io
    im = Image.new("RGB", (100, 200), (10, 200, 10)); b = _io.BytesIO(); im.save(b, "PNG")
    key = storage().put("base/smith1909/major-00.png", b.getvalue(), "image/png")
    from routers.deps import store
    bc = store().get("base_cards", "bc_smith1909_major-00"); bc["image_url"] = f"/media/{key}"; store().put("base_cards", bc)
    r2 = client.patch(f"/api/symbols/{crown['id']}", json={"exemplar_from_base_card": {"base_card_id": bc["id"], "bbox": [0.1, 0.1, 0.6, 0.4]}}, headers=ctx["cur"]["h"]).json()
    assert r2["exemplar"]["origin"] == "base_crop" and r2["exemplar"]["source_ref"] == bc["id"]
    img = client.get(r2["exemplar"]["image_url"]).content
    w, h = Image.open(_io.BytesIO(img)).size
    assert (w, h) == (50, 60)


def test_merge_rewrites_references_and_retire_hides(client, ctx):
    did = ctx["deck"]["id"]
    syms = {s["key"]: s for s in client.get(f"/api/decks/{did}/symbols").json()}
    a, b = syms["downward_water"], syms["downward_water_2"]
    # plant a version that references both
    from routers.deps import store
    from models import Card, Version
    card = Card(id="c_m", deck_id=did, position_key="major-05", maker_id=ctx["cur"]["user"]["id"], current_version_id="v_m")
    ver = Version(id="v_m", card_id="c_m", deck_id=did, image_url="x.png", symbols_declared=[{"symbol_id": a["id"]}, {"symbol_id": b["id"]}],
                  symbols_detected=[{"symbol_id": b["id"], "salience": 0.7}])
    store().put("cards", card.to_doc()); store().put("versions", ver.to_doc())
    r = client.post(f"/api/symbols/{b['id']}/merge", json={"into_symbol_id": a["id"]}, headers=ctx["cur"]["h"]).json()
    assert r["versions_rewritten"] == 1
    v = store().get("versions", "v_m")
    assert [x["symbol_id"] for x in v["symbols_declared"]] == [a["id"]] and v["symbols_detected"][0]["symbol_id"] == a["id"]
    merged = client.get(f"/api/symbols/{b['id']}").json()
    assert merged["status"] == "merged" and merged["merged_into_symbol_id"] == a["id"]
    assert client.get(f"/api/symbols/{a['id']}").json()["cards"][0]["card_id"] == "c_m"
    active = [s["key"] for s in client.get(f"/api/decks/{did}/symbols").json()]
    assert "downward_water_2" not in active and "downward_water" in active
    r2 = client.post(f"/api/symbols/{syms['tower']['id']}/retire", headers=ctx["cur"]["h"]).json()
    assert r2["status"] == "retired"
    assert "tower" not in [s["key"] for s in client.get(f"/api/decks/{did}/symbols").json()]
    assert "tower" in [s["key"] for s in client.get(f"/api/decks/{did}/symbols?status=all").json()]
    assert client.post(f"/api/symbols/{a['id']}/merge", json={"into_symbol_id": a["id"]}, headers=ctx["cur"]["h"]).status_code == 422
    assert client.post(f"/api/symbols/{a['id']}/retire", headers=ctx["mem"]["h"]).status_code == 403


def test_set_measured(client, ctx):
    from routers.deps import store
    from service.symbols import set_measured
    did = ctx["deck"]["id"]
    sid = client.get(f"/api/decks/{did}/symbols").json()[0]["id"]
    assert set_measured(store(), did, {sid: {"coef": [0.5] * 8, "n_readings": 12, "coherence": "consistent"}}) == 1
    m = client.get(f"/api/symbols/{sid}").json()["measured"]
    assert m["coef"] == [0.5] * 8 and m["coherence"] == "consistent" and m["n_readings"] == 12

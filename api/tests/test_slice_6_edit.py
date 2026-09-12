"""Slice 6 — Edit menu: one-op edits with fidelity ≥ 0.85 on ≥ 8/10 cards, the version lock (409 version_stale),
cosmetic ops as non-experiments, approval gates, restore, compare heatmap."""
import base64
import os

import pytest

os.environ["PIXIE_IMAGE_PROVIDER"] = "local"
os.environ["PIXIE_IMAGE_EMBED"] = "perceptual"
os.environ["PIXIE_DETECT"] = "fallback"
os.environ["PIXIE_RATE_LIMIT_JOBS"] = "1000"  # the per-user rate limit is exercised in test_rate_limit below

from tests.test_slice_5_generate import card_png, localize_base, make_deck, symbols_of  # noqa: E402
from tests.v5util import guest, login, make_client, seed_base  # noqa: E402

FAR = [3, 3, 3, 3, 3, 3, 3, 3]


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with make_client(tmp_path_factory.mktemp("s6")) as c:
        seed_base(c, n_cards=22)
        localize_base(c)
        yield c


@pytest.fixture(scope="module")
def ctx(client):
    maker = login(client, "maker6@example.org", "Maker")
    editor = login(client, "editor6@example.org", "Editor")
    stranger = login(client, "stranger6@example.org", "Stranger")
    deck = make_deck(client, maker["h"], name="Edit deck", threshold=3)
    client.post(f"/api/decks/{deck['id']}/members", json={"user_id": editor["user"]["id"], "role": "member"}, headers=maker["h"])
    client.post(f"/api/decks/{deck['id']}/members", json={"user_id": stranger["user"]["id"], "role": "member"}, headers=maker["h"])
    return {"maker": maker, "editor": editor, "stranger": stranger, "deck": deck, "syms": symbols_of(client, deck["id"], maker["h"])}


def upload_card(client, ctx, position_key, symbol_key="crown"):
    h, syms = ctx["maker"]["h"], ctx["syms"]
    card = client.post(f"/api/decks/{ctx['deck']['id']}/cards", json={"position_key": position_key, "intent": {"statement": "a quiet ending", "axes": [1, 3, -1, -2, 0, -3, 1, -2]}}, headers=h).json()
    r = client.post(f"/api/cards/{card['id']}/generate", json={"mode": "upload", "image_base64": base64.b64encode(card_png()).decode(), "rights_attested": True,
                                                              "symbols": [syms[symbol_key]["id"]]}, headers=h)
    assert r.status_code == 202, r.text
    return client.get(f"/api/cards/{card['id']}", headers=h).json()


def open_by_store(card_id):
    from routers.deps import store

    c = store().get("cards", card_id)
    c["status"] = "open"
    store().put("cards", c)


def test_readings_open_the_card(client, ctx):
    card = upload_card(client, ctx, "major-00")
    vid = card["current_version_id"]
    assert card["status"] == "reading"
    for i in range(3):
        g = guest(client, f"reader{i}")
        r = client.post(f"/api/versions/{vid}/readings", json={"axes": FAR}, headers=g["h"])
        assert r.status_code == 200, r.text
    view = client.get(f"/api/cards/{card['id']}", headers=ctx["maker"]["h"]).json()
    assert view["status"] == "open" and view["readings"]["ready"] and view["can"]["edit"] is True  # any_member policy: the maker may run experiments too
    ctx["card_open"] = card["id"]


def test_add_symbol_fidelity_on_ten_cards(client, ctx):
    h, syms = ctx["editor"]["h"], ctx["syms"]
    keys = [f"major-{i:02d}" for i in range(1, 11)]
    scores = []
    for k in keys:
        card = upload_card(client, ctx, k)
        open_by_store(card["id"])
        r = client.post(f"/api/cards/{card['id']}/edit", json={"op": "add", "symbol_id": syms["sun"]["id"], "placement": "top", "rationale": "the sun should read as gain",
                                                              "bet_axis": 4, "n": 1, "base_version_id": card["current_version_id"]}, headers=h)
        assert r.status_code == 202, r.text
        out = r.json()
        assert out["job"]["status"] == "done", out["job"]
        cands = client.get(f"/api/versions/{out['version_id']}/candidates", headers=h).json()
        assert cands["counts_as_experiment"] is True and cands["candidates"]
        best = cands["candidates"][0]
        scores.append(best["fidelity"])
        assert best["heatmap_url"].startswith("/media/") and best["containment"] is not None
        ctx.setdefault("edits", []).append((card["id"], out["version_id"], card["current_version_id"]))
    assert sum(1 for s in scores if s >= 0.85) >= 8, scores


def test_choose_edit_and_lock(client, ctx):
    h = ctx["editor"]["h"]
    card_id, vid, v0 = ctx["edits"][0]
    r = client.post(f"/api/versions/{vid}/choose", json={"index": 0}, headers=h)
    assert r.status_code == 200, r.text
    card = r.json()["card"]
    assert card["status"] == "reading" and card["current_version_id"] == vid and card["n_versions"] == 2
    assert ctx["editor"]["user"]["id"] in card["encoder_ids"]
    v = r.json()["version"]
    assert v["v"] == 1 and v["base_version_id"] == v0 and v["how"]["op"] == "add" and v["checks"]["fidelity"] >= 0.85
    # the editor is now an encoder: sees the intent
    assert client.get(f"/api/cards/{card_id}", headers=h).json()["intent"]["statement"] == "a quiet ending"
    # stale lock: editing against v0 now that v1 is the head
    open_by_store(card_id)
    r = client.post(f"/api/cards/{card_id}/edit", json={"op": "remove", "symbol_id": ctx["syms"]["sun"]["id"], "rationale": "too loud", "bet_axis": 4,
                                                       "base_version_id": v0}, headers=h)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "version_stale" and r.json()["detail"]["head_version_id"] == vid
    # a version list is a graph with one edge
    g = client.get(f"/api/cards/{card_id}/versions").json()
    assert len(g["versions"]) == 2 and g["edges"] == [{"from": v0, "to": vid}]


def test_cosmetic_and_validation(client, ctx):
    h, syms = ctx["editor"]["h"], ctx["syms"]
    card_id, _, _ = ctx["edits"][1]
    head = client.get(f"/api/cards/{card_id}", headers=h).json()["current_version_id"]
    # cosmetic: no bet, no symbol, not an experiment
    r = client.post(f"/api/cards/{card_id}/edit", json={"op": "cosmetic", "how_text": "cleaner lines, warmer paper", "rationale": "tidy", "n": 1, "base_version_id": head}, headers=h)
    assert r.status_code == 202, r.text
    cands = client.get(f"/api/versions/{r.json()['version_id']}/candidates", headers=h).json()
    assert cands["counts_as_experiment"] is False and cands["candidates"]
    # experiments need a bet and a rationale; how_text may not name an unselected symbol
    card2, _, _ = ctx["edits"][2]
    head2 = client.get(f"/api/cards/{card2}", headers=h).json()["current_version_id"]
    assert client.post(f"/api/cards/{card2}/edit", json={"op": "add", "symbol_id": syms["sun"]["id"], "rationale": "x", "base_version_id": head2}, headers=h).status_code == 422
    assert client.post(f"/api/cards/{card2}/edit", json={"op": "add", "symbol_id": syms["sun"]["id"], "bet_axis": 1, "base_version_id": head2}, headers=h).status_code == 422
    r = client.post(f"/api/cards/{card2}/edit", json={"op": "add", "symbol_id": syms["sun"]["id"], "bet_axis": 1, "rationale": "x", "how_text": "with a tower behind", "base_version_id": head2}, headers=h)
    assert r.status_code == 422 and "tower" in r.text.lower()
    # replace needs a target; removing something not on the card fails
    assert client.post(f"/api/cards/{card2}/edit", json={"op": "replace", "symbol_id": syms["crown"]["id"], "bet_axis": 1, "rationale": "x", "base_version_id": head2}, headers=h).status_code == 422
    assert client.post(f"/api/cards/{card2}/edit", json={"op": "remove", "symbol_id": syms["tower"]["id"], "bet_axis": 1, "rationale": "x", "base_version_id": head2}, headers=h).status_code == 422


def test_approval_gate(client, ctx):
    maker, stranger = ctx["maker"], ctx["stranger"]
    deck = make_deck(client, maker["h"], name="Maker list deck", policy="maker_list")
    syms = symbols_of(client, deck["id"], maker["h"])
    client.post(f"/api/decks/{deck['id']}/members", json={"user_id": stranger["user"]["id"], "role": "member"}, headers=maker["h"])
    card = client.post(f"/api/decks/{deck['id']}/cards", json={"position_key": "major-00", "intent": {"statement": "s", "axes": [0] * 8}}, headers=maker["h"]).json()
    client.post(f"/api/cards/{card['id']}/generate", json={"mode": "upload", "image_base64": base64.b64encode(card_png()).decode(), "rights_attested": True, "symbols": [syms["crown"]["id"]]}, headers=maker["h"])
    open_by_store(card["id"])
    head = client.get(f"/api/cards/{card['id']}", headers=maker["h"]).json()["current_version_id"]
    body = {"op": "add", "symbol_id": syms["sun"]["id"], "bet_axis": 4, "rationale": "x", "n": 1, "base_version_id": head}
    assert client.post(f"/api/cards/{card['id']}/edit", json=body, headers=stranger["h"]).status_code == 403
    # request → maker approves the person → edit allowed
    req = client.post(f"/api/cards/{card['id']}/edit-requests", json={"note": "let me try the sun"}, headers=stranger["h"]).json()
    assert req["status"] == "open"
    assert client.patch(f"/api/cards/{card['id']}/edit-requests/{req['id']}", json={"action": "approve"}, headers=stranger["h"]).status_code == 403
    assert client.patch(f"/api/cards/{card['id']}/edit-requests/{req['id']}", json={"action": "approve"}, headers=maker["h"]).json()["status"] == "approved"
    assert client.get(f"/api/cards/{card['id']}", headers=maker["h"]).json()["approved_editors"] == [stranger["user"]["id"]]
    assert client.post(f"/api/cards/{card['id']}/edit", json=body, headers=stranger["h"]).status_code == 202
    # the maker may narrow the list back; a card that is not open rejects edits
    assert client.patch(f"/api/cards/{card['id']}", json={"approved_editors": []}, headers=maker["h"]).status_code == 200
    assert client.post(f"/api/cards/{card['id']}/edit", json=body, headers=stranger["h"]).status_code == 403


def test_restore_and_compare(client, ctx):
    h = ctx["editor"]["h"]
    card_id, v1, v0 = ctx["edits"][0]
    r = client.post(f"/api/versions/{v0}/restore", json={"note": "back to the plain card"}, headers=h)
    assert r.status_code == 201, r.text
    nv = r.json()["version"]
    assert nv["how"]["op"] == "cosmetic" and nv["how"]["counts_as_experiment"] is False and nv["v"] == 2 and nv["base_version_id"] == v1
    assert r.json()["card"]["current_version_id"] == nv["id"]
    cmp = client.get(f"/api/versions/{v0}/compare/{v1}", headers=h).json()
    assert 0 <= cmp["fidelity"] <= 1 and cmp["heatmap_url"].startswith("/media/")
    img = client.get(cmp["heatmap_url"])
    assert img.status_code == 200 and img.headers["content-type"].startswith("image/png") and img.content[:8] == b"\x89PNG\r\n\x1a\n"
    same = client.get(f"/api/versions/{v0}/compare/{nv['id']}", headers=h).json()
    assert same["fidelity"] > 0.99  # the restored image is byte-identical


def test_branch_and_reinterpret(client, ctx):
    h = ctx["maker"]["h"]  # owner ≥ curator
    card_id, v1, v0 = ctx["edits"][3]
    r = client.post(f"/api/cards/{card_id}/branches", json={"from_version_id": v0, "branch_key": "alt"}, headers=h)
    assert r.status_code == 201 and any(b["branch_key"] == "alt" and b["head_version_id"] == v0 for b in r.json()["branches"])
    assert client.post(f"/api/cards/{card_id}/branches", json={"from_version_id": v0}, headers=ctx["editor"]["h"]).status_code == 403
    r = client.post(f"/api/decks/{ctx['deck']['id']}/reinterpret", json={"base_deck_slug": "smith1909", "positions": ["major-20", "major-21"], "n": 1}, headers=h)
    assert r.status_code == 202, r.text
    job = r.json()["job"]
    assert job["status"] == "done" and len(job["result"]["done"]) == 2 and job["result"]["failed"] == []
    tiles = {t["position_key"]: t for t in client.get(f"/api/decks/{ctx['deck']['id']}/cards").json()}
    assert tiles["major-20"]["status"] == "draft" and tiles["major-20"]["image_url"].startswith("/media/") and not tiles["major-20"]["has_intent"]
    v = client.get(f"/api/cards/{tiles['major-21']['id']}", headers=h).json()["current_version"]
    assert v["how"]["mode"] == "reinterpret" and v["how"]["provider"] == "local"


def test_rate_limit(client, ctx):
    os.environ["PIXIE_RATE_LIMIT_JOBS"] = "1"
    try:
        h, syms = ctx["editor"]["h"], ctx["syms"]
        card_id, _, _ = ctx["edits"][4]
        head = client.get(f"/api/cards/{card_id}", headers=h).json()["current_version_id"]
        open_by_store(card_id)
        r = client.post(f"/api/cards/{card_id}/edit", json={"op": "cosmetic", "rationale": "x", "n": 1, "base_version_id": head}, headers=h)
        assert r.status_code == 429 and r.json()["detail"]["code"] == "rate_limited"
    finally:
        os.environ["PIXIE_RATE_LIMIT_JOBS"] = "1000"

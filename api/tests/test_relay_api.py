"""End-to-end relay over HTTP: create → join → start → compose → read → reveal → edit → read → reveal → chains → replay,
plus deck mode (T2): compose, read queue, lock. Memory store, throwaway snapshot, hash embedder."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.dirname(HERE)
sys.path.insert(0, API)
os.environ.setdefault("PIXIE_EMBED", "hash")
os.environ.setdefault("PIXIE_N_BOOT", "30")
DATA = os.path.join(API, "..", "data")
pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(DATA, "libraries.json")), reason="data/libraries.json not built yet")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["PIXIE_SNAPSHOT"] = str(tmp_path_factory.mktemp("state") / "state.json")
    os.environ.pop("MONGODB_URI", None)
    import importlib
    import main as m

    importlib.reload(m)
    from fastapi.testclient import TestClient

    with TestClient(m.app) as c:
        yield c


def post(client, path, body, status=200):
    r = client.post(path, json=body)
    assert r.status_code == status, (path, r.status_code, r.text[:300])
    return r.json()


def test_health_and_seeds(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["n_libraries"] >= 3 and h["n_elements"] >= 80
    assert h["n_synthetic"] >= 600 and h["n_real"] == 0 and h["n_cards"] >= 60
    assert h["planted"]["polysemous_card_id"] != h["planted"]["noisy_card_id"]
    assert h["playground"]["code"] == "PLAY"


def test_picker_and_planted_verdicts(client):
    p = client.get("/api/decks/PLAY/elements").json()
    libs = {x["library"]["id"]: x["elements"] for x in p["libraries"]}
    assert "smith1909" in libs and len(libs["smith1909"]) >= 40
    e = libs["smith1909"][0]
    assert e["image_url"].startswith("/static/") and e["caption"] and e["size_class"] in ("large", "small")
    planted = client.get("/api/health").json()["planted"]
    for cid, expect in ((planted["polysemous_card_id"], "polysemous"), (planted["noisy_card_id"], "noisy")):
        ch = client.get(f"/api/decks/PLAY/cards/{cid}").json()
        assert ch["card"]["synthetic"] is True
        # verdict is per version; the chain's v0 has ≥ 12 readings
        assert ch["versions"][0]["n_readings"] >= 8
    g = client.get("/api/decks/PLAY/grammar").json()
    assert g["n_edits"] >= 40 and any(x["n_edits"] > 0 for x in g["elements"])
    assert all(x["historical_support"] is not None for x in g["elements"] if x["origin"] == "cut")


def _pick(client):
    p = client.get("/api/decks/PLAY/elements").json()
    els = [x for lib in p["libraries"] for x in lib["elements"] if lib["library"]["id"] == "smith1909"]
    large = [e for e in els if e["size_class"] == "large"]
    small = [e for e in els if e["size_class"] == "small"]
    return large, small


def test_full_relay(client):
    large, small = _pick(client)
    r = post(client, "/api/rooms", {"nickname": "ana"})
    code, ana = r["room"]["code"], r["guest_id"]
    bo = post(client, f"/api/rooms/{code}/join", {"nickname": "bo"})["guest_id"]
    cy = post(client, f"/api/rooms/{code}/join", {"nickname": "cy"})["guest_id"]
    di = post(client, f"/api/rooms/{code}/join", {"nickname": "di"})["guest_id"]
    post(client, f"/api/rooms/{code}/start", {"guest_id": bo}, 403)
    room = post(client, f"/api/rooms/{code}/start", {"guest_id": ana})
    assert room["phase"] == "compose" and room["you"]["role"] == "maker"

    # small in center is rejected; valid composition accepted
    bad = {"guest_id": ana, "statement": "x", "axes": [0] * 8, "elements": [{"element_id": small[0]["element_id"], "slot": "center"}, {"element_id": small[1]["element_id"], "slot": "top"}]}
    post(client, f"/api/rooms/{code}/compose", bad, 422)
    els = [{"element_id": large[0]["element_id"], "slot": "center"}, {"element_id": small[0]["element_id"], "slot": "top"}, {"element_id": small[1]["element_id"], "slot": "left"}]
    intent_axes = [1, 2, -3, 1, -1, -2, -1, -2]
    room = post(client, f"/api/rooms/{code}/compose", {"guest_id": ana, "statement": "letting go, gently", "axes": intent_axes, "elements": els})
    assert room["phase"] == "read" and room["round"]["v"] == 0 and len(room["round"]["version"]["elements"]) == 3
    assert "intent" in room  # the holder sees their intent while the card is out
    rv = client.get(f"/api/rooms/{code}", params={"guest_id": bo}).json()
    assert rv["you"]["role"] == "reader" and "intent" not in rv and rv["round"]["version"]["elements"][0]["image_url"]
    assert rv["you"]["previous_axes"] is None

    post(client, f"/api/rooms/{code}/reading", {"guest_id": ana, "axes": [0] * 8}, 400)
    room = post(client, f"/api/rooms/{code}/reading", {"guest_id": bo, "axes": [1, 2, -3, 2, -1, -1, -1, -2], "free_text": "release"})
    assert room["phase"] == "read"
    room = post(client, f"/api/rooms/{code}/reading", {"guest_id": di, "axes": [1, 1, -2, 1, 0, -2, 0, -2]})
    assert room["phase"] == "read"
    room = post(client, f"/api/rooms/{code}/reading", {"guest_id": cy, "axes": [2, -1, 1, -2, 2, 2, 2, -3]})
    assert room["phase"] == "reveal"
    rev = room["reveal"]
    assert rev["card"]["v"] == 0 and rev["maker_score"]["n"] == 3 and rev["maker_score"]["points"] == 3  # two in, one out
    assert rev["fidelity"] is not None and len(rev["gaps_abs"]) == 8 and rev["gaps_abs"][0]["abs"] >= rev["gaps_abs"][-1]["abs"]
    assert rev["edit_effect"] is None and rev["landing"] is None and rev["card"]["status"] == "reading"
    assert rev["grammar_strip"] and rev["grammar_strip_before"] and len(rev["grammar_strip"]) == 3
    assert rev["readings"][0]["nickname"] == "bo" and rev["readings"][1]["nickname"] == "di"  # submission order
    assert rev["verdict"]["verdict"] == "collecting"
    assert rev["you"]["d_total"] is not None  # cy's own distance
    rv = client.get(f"/api/rooms/{code}", params={"guest_id": bo}).json()
    assert rv["reveal"]["card"]["statement"] is None and rv["reveal"]["gaps_signed"] is None  # readers: not public yet
    assert room["scores"][ana] == 3

    # continue → edit by bo (next after ana in join order)
    room = post(client, f"/api/rooms/{code}/continue", {"guest_id": ana})
    assert room["phase"] == "edit" and room["round"]["editor_id"] == bo
    ev = client.get(f"/api/rooms/{code}", params={"guest_id": bo}).json()
    assert ev["you"]["role"] == "editor" and ev["intent"]["statement"] and len(ev["intent"]["gaps_signed"]) == 8
    # illegal: swap a small into center
    post(client, f"/api/rooms/{code}/edit", {"guest_id": bo, "type": "swap", "element_id": large[0]["element_id"], "to_element_id": small[2]["element_id"], "bet_axis": 3}, 422)
    post(client, f"/api/rooms/{code}/edit", {"guest_id": cy, "type": "add", "element_id": small[3]["element_id"], "bet_axis": 3}, 403)
    room = post(client, f"/api/rooms/{code}/edit", {"guest_id": bo, "type": "swap", "element_id": small[0]["element_id"], "to_element_id": small[2]["element_id"], "bet_axis": 4, "rationale": "the sun reads as gain"})
    assert room["phase"] == "read" and room["round"]["v"] == 1
    assert {e["element_id"] for e in room["round"]["version"]["elements"]} == {large[0]["element_id"], small[2]["element_id"], small[1]["element_id"]}
    assert room["round"]["version"]["edit"]["editor_nickname"] == "bo"
    # readers now: ana (maker) and cy; cy has previous axes
    cv = client.get(f"/api/rooms/{code}", params={"guest_id": cy}).json()
    assert cv["you"]["role"] == "reader" and cv["you"]["previous_axes"] == [2, -1, 1, -2, 2, 2, 2, -3]
    room = post(client, f"/api/rooms/{code}/reading", {"guest_id": cy, "axes": [1, 2, -3, 1, -1, -2, -1, -2]})  # cy moves onto the intent
    room = post(client, f"/api/rooms/{code}/reading", {"guest_id": di, "axes": [1, 2, -3, 1, -1, -2, -1, -2]})
    room = post(client, f"/api/rooms/{code}/reading", {"guest_id": ana, "axes": [1, 2, -3, 1, -1, -2, -1, -2]})
    assert room["phase"] == "reveal"
    rev = room["reveal"]
    assert rev["card"]["v"] == 1 and rev["maker_score"] is None and rev["edit_effect"]["bet_axis"] == 4
    assert rev["edit_effect"]["n_pairs"] == 2 and rev["edit_effect"]["delta"] is not None
    cy_r = next(x for x in rev["readings"] if x["nickname"] == "cy")
    assert cy_r["prev_xy"] is not None and cy_r["shift"] is not None
    assert rev["edited_element_id"] == small[2]["element_id"]
    assert rev["fidelity"] >= 0.8 and rev["landing"] and rev["card"]["status"] == "landed"
    assert set(rev["landing"]["encoders"]) == {"ana", "bo"}
    assert rev["card"]["statement"] == "letting go, gently"  # public once landed
    # points: ana 3 (maker) +1 landing; bo +1 landing (+2 if bet hit)
    assert room["scores"][ana] == 4 and room["scores"].get(bo, 0) >= 1
    ch = client.get(f"/api/rooms/{code}/chains").json()
    assert len(ch) == 1 and ch[0]["card"]["landed"] and len(ch[0]["versions"]) == 2 and ch[0]["versions"][1]["edit"]["rationale"]
    assert ch[0]["card"]["title"]

    room = post(client, f"/api/rooms/{code}/continue", {"guest_id": ana})
    assert room["phase"] == "compose" and room["round"]["maker_id"] == bo
    assert client.get("/api/health").json()["n_real"] == 6
    home = client.get("/api/decks/PLAY").json()
    assert len(home["cards"]["landed"]) == 1 and home["n_synthetic_cards"] >= 60

    # replay the landed card while bo is composing: not allowed mid-compose → 400; so test on a fresh room
    r2 = post(client, "/api/rooms", {"nickname": "host2"})
    code2, host2 = r2["room"]["code"], r2["guest_id"]
    post(client, f"/api/rooms/{code2}/join", {"nickname": "z"})
    room = post(client, f"/api/rooms/{code2}/replay", {"guest_id": host2})
    assert room["phase"] == "read" and room["round"]["replay"] and room["round"]["v"] == 0 and room["round"]["n_readers"] == 3
    assert client.get("/api/health").json()["n_real"] == 6
    bw = client.get("/api/decks/PLAY/bandwidth").json()
    assert bw and bw[0]["n_elements"] == 3


def test_deck_mode_lock(client):
    large, small = _pick(client)
    d = post(client, "/api/decks", {"name": "Lunch deck", "libraries": ["smith1909"], "nickname": "owner"})
    owner, code = d["guest_id"], d["deck"]["deck"]["code"]
    m1 = post(client, f"/api/decks/{code}/join", {"nickname": "m1"})["guest_id"]
    m2 = post(client, f"/api/decks/{code}/join", {"nickname": "m2"})["guest_id"]
    els = [{"element_id": large[1]["element_id"], "slot": "center"}, {"element_id": small[4]["element_id"], "slot": "bottom"}]
    ch = post(client, f"/api/decks/{code}/cards", {"guest_id": owner, "statement": "a slow beginning", "axes": [-2, -3, 0, 1, -1, -1, 1, 0], "elements": els})
    cid = ch["card"]["id"]
    assert ch["card"]["status"] == "reading" and ch["card"]["approved_editors"] == "*"
    q = client.get(f"/api/decks/{code}/read", params={"guest_id": m1}).json()
    assert not q["empty"] and q["card_id"] == cid and q["version"]["v"] == 0
    for g in ("r1", "r2", "r3"):
        gid = post(client, f"/api/decks/{code}/join", {"nickname": g})["guest_id"]
        out = post(client, f"/api/decks/{code}/cards/{cid}/readings", {"guest_id": gid, "axes": [2, 2, 2, 2, 2, 2, 2, 2]})
    assert out["status"] == "open"  # threshold 3 reached, far from the intent → open for an edit
    assert client.get(f"/api/decks/{code}/read", params={"guest_id": m2}).json()["empty"]
    stale = client.get(f"/api/decks/{code}/cards/{cid}").json()["card"]["latest_version_id"]
    ch = post(client, f"/api/decks/{code}/cards/{cid}/edit", {"guest_id": m1, "version_id": stale, "type": "add", "element_id": small[5]["element_id"], "bet_axis": 1, "rationale": "needs an ending"})
    assert ch["card"]["status"] == "reading" and len(ch["versions"]) == 2
    post(client, f"/api/decks/{code}/cards/{cid}/edit", {"guest_id": m2, "version_id": stale, "type": "remove", "element_id": small[4]["element_id"], "bet_axis": 0}, 409)
    # approvals: maker restricts editors
    post(client, f"/api/decks/{code}/cards/{cid}/approved_editors", {"guest_id": m1, "approved_editors": [m2]}, 403)
    ch = post(client, f"/api/decks/{code}/cards/{cid}/approved_editors", {"guest_id": owner, "approved_editors": [m2]})
    assert ch["card"]["approved_editors"] == [m2]

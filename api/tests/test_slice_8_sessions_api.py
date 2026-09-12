"""Slice 8 over HTTP: relay session with a live edit through the cards service (inline worker, local provider)."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("PIXIE_EMBED", "hash")
os.environ["PIXIE_WORKER"] = "inline"
os.environ["PIXIE_IMAGE_PROVIDER"] = "local"
os.environ["PIXIE_IMAGE_EMBED"] = "perceptual"
os.environ["PIXIE_DETECT"] = "fallback"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["PIXIE_SNAPSHOT"] = str(tmp_path_factory.mktemp("state") / "state.json")
    import importlib
    import main as m

    importlib.reload(m)
    from fastapi.testclient import TestClient

    with TestClient(m.app) as c:
        yield c


def login(client, email, name=None):
    t = client.post("/api/auth/magic", json={"email": email, "name": name or email.split("@")[0]}).json()["token"]
    r = client.get(f"/api/auth/magic/{t}", follow_redirects=False)
    tok = r.json()["token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {tok}"}


def guest(client, name):
    tok = client.post("/api/auth/guest", json={"name": name}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_relay_session_with_live_edit(client):
    host = login(client, "host@example.com", "host")
    deck = client.post("/api/decks", json={"name": "Session deck", "visibility": "public", "origin": {"kind": "base", "base_deck_id": "bd_smith1909"},
                                           "structure_template_id": "majors22", "card_mode": "reference", "settings": {"default_editor_policy": "any_member"}}, headers=host).json()
    did = deck["id"]
    syms = client.get(f"/api/decks/{did}/symbols", headers=host).json()
    keys = {s["key"]: s["id"] for s in syms}
    # host makes a card: generate (local) → choose → intent
    card = client.post(f"/api/decks/{did}/cards", json={"position_key": "major-17", "title": "The Star"}, headers=host).json()
    cid = card["id"]
    r = client.post(f"/api/cards/{cid}/generate", json={"mode": "prompt", "prompt_user": "a figure pouring water under a star", "symbols": [{"symbol_id": keys["star"]}, {"symbol_id": keys["nude_figure"]}, {"symbol_id": keys["water_falling"]}], "n": 1}, headers=host)
    assert r.status_code in (200, 202), r.text
    vid = r.json()["version_id"]
    r = client.post(f"/api/versions/{vid}/choose", json={"index": 0, "candidate_index": 0}, headers=host)
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/cards/{cid}", json={"intent": {"statement": "letting go, gently", "axes": [1, 2, -3, 1, -1, -2, -1, -2]}}, headers=host)
    assert r.status_code == 200 and r.json()["status"] == "reading", r.text
    # members join the deck and the session
    p1, p2 = login(client, "p1@example.com", "p1"), login(client, "p2@example.com", "p2")
    for h in (p1, p2):
        client.post(f"/api/decks/{did}/join", headers=h)  # may 404; invitations are the formal path
    for h in (p1, p2):  # one link invitation per member (single use)
        inv = client.post(f"/api/decks/{did}/invitations", json={"link": True, "role": "member"}, headers=host).json()
        tok = inv.get("link_token") or inv.get("token") or (inv.get("accept_url") or "").rsplit("/", 2)[-2]
        rr = client.post(f"/api/invitations/{tok}/accept", headers=h)
        assert rr.status_code in (200, 201), rr.text
    g = guest(client, "judge")
    s = client.post(f"/api/decks/{did}/sessions", json={"mode": "relay", "nickname": "host"}, headers=host).json()
    code, sid = s["code"], s["id"]
    for h in (p1, p2, g):
        assert client.post("/api/sessions/join", json={"code": code, "nickname": "x"}, headers=h).status_code == 200
    s = client.post(f"/api/sessions/{sid}/start", json={}, headers=host).json()
    assert s["state"] == "compose" and s["current_maker_id"]
    s = client.post(f"/api/sessions/{sid}/choose", json={"card_id": cid}, headers=host).json()
    assert s["state"] == "read" and s["round"]["n_readers"] == 3
    rid = s["round"]["id"]
    for h, ax in ((p1, [1, 2, -3, 2, -1, -1, -1, -2]), (p2, [0, 1, -2, 2, 0, -2, 0, -1]), (g, [2, -1, 1, -2, 2, 2, 2, -3])):
        s = client.post(f"/api/sessions/{sid}/rounds/{rid}/submit", json={"axes": ax}, headers=h).json()
    assert s["state"] == "reveal" and s["reveal"]["maker_score"] is None  # readers never see the maker's score panel
    hv = client.get(f"/api/sessions/{sid}", headers=host).json()
    assert hv["reveal"]["maker_score"]["points"] == 3 and hv["reveal"]["card"]["statement"] == "letting go, gently"
    assert s["scores"].get(s["host_id"]) == 3
    s = client.post(f"/api/sessions/{sid}/advance", json={}, headers=host).json()
    assert s["state"] == "edit" and s["current_editor_id"]
    editor = p1 if s["current_editor_id"] == client.get("/api/me", headers=p1).json()["user"]["id"] else p2
    ev = client.get(f"/api/sessions/{sid}", headers=editor).json()
    assert ev["you"]["role"] == "editor" and len(ev["intent"]["gaps_signed"]) == 8
    # live edit: add the sun → job runs inline → auto-chosen → paired re-read
    r = client.post(f"/api/sessions/{sid}/edit", json={"op": "add", "symbol_id": keys["sun"], "bet_axis": 4, "rationale": "sun pulls toward gain"}, headers=editor)
    assert r.status_code == 200, r.text
    s = r.json()["session"]
    assert s["state"] == "read", s["state"]
    assert s["version"]["v"] == 1 and s["edits_this_card"] == 1
    rid2 = s["round"]["id"]
    readers = [h for h in (p1, p2, g) if h is not editor]
    for h in readers:
        s = client.post(f"/api/sessions/{sid}/rounds/{rid2}/submit", json={"axes": [1, 2, -3, 1, -1, -2, -1, -2]}, headers=h).json()
    assert s["state"] == "reveal"
    rev = s["reveal"]
    assert rev["edit_effect"]["bet_axis"] == 4 and rev["edit_effect"]["n_pairs"] >= 1 and rev["edit_effect"].get("editor_nickname")
    assert rev["landing"] and rev["card"]["status"] == "landed"
    s = client.post(f"/api/sessions/{sid}/advance", json={}, headers=host).json()
    assert s["state"] == "compose"
    s = client.post(f"/api/sessions/{sid}/end", json={}, headers=host).json()
    assert s["state"] == "ended" and len(s["summary"]["cards"]) == 2

"""Small decks must not deadlock: the reading threshold adapts to the members who can read, and the maker
(or a curator) may open a card for edits once it has one reading."""
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


def guest(client, name):
    client.cookies.clear()  # the guest endpoint is idempotent per session: a fresh guest needs a fresh cookie jar
    tok = client.post("/api/auth/guest", json={"name": name}).json()["token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {tok}"}


def make_card(client, h, did, key):
    card = client.post(f"/api/decks/{did}/cards", json={"position_key": key}, headers=h).json()
    syms = client.get(f"/api/decks/{did}/symbols", headers=h).json()
    r = client.post(f"/api/cards/{card['id']}/generate", json={"mode": "prompt", "prompt_user": "x", "symbols": [syms[0]["id"], syms[1]["id"]], "n": 1}, headers=h).json()
    client.post(f"/api/versions/{r['version_id']}/choose", json={"index": 0}, headers=h)
    client.patch(f"/api/cards/{card['id']}", json={"intent": {"statement": "s", "axes": [1, 1, 1, 1, 1, 1, 1, 1]}}, headers=h)
    return client.get(f"/api/cards/{card['id']}", headers=h).json()


def test_two_person_deck_opens_after_one_reading(client):
    owner, mate = guest(client, "owner"), guest(client, "mate")
    d = client.post("/api/decks", json={"name": "Two of us", "visibility": "private", "origin": {"kind": "base", "base_deck_id": "bd_smith1909"}, "structure_template_id": "majors22", "card_mode": "reference"}, headers=owner).json()
    inv = client.post(f"/api/decks/{d['id']}/invitations", json={"link": True, "role": "member"}, headers=owner).json()
    tok = inv.get("link_token") or inv.get("token") or (inv.get("accept_url") or "").split("/")[-2]
    assert client.post(f"/api/invitations/{tok}/accept", headers=mate).status_code in (200, 201)
    c = make_card(client, owner, d["id"], "major-00")
    assert c["status"] == "reading" and c["readings"]["threshold"] == 1  # one eligible reader → threshold 1
    q = client.get(f"/api/decks/{d['id']}/read/next", headers=mate).json()
    assert not q["empty"] and q["card_id"] == c["id"] and q["ready_threshold"] == 1
    # the maker cannot read their own card; the queue says why it is empty for them
    qo = client.get(f"/api/decks/{d['id']}/read/next", headers=owner).json()
    assert qo["empty"] and qo["reason"] == "own_cards_only"
    r = client.post(f"/api/versions/{c['current_version_id']}/readings", json={"axes": [3, 3, 3, 3, 3, 3, 3, 3]}, headers=mate)
    assert r.status_code == 200 and r.json()["card_status"] == "open"
    q2 = client.get(f"/api/decks/{d['id']}/read/next", headers=mate).json()
    assert q2["empty"] and q2["reason"] in ("all_read", "no_cards")
    # the mate may now edit
    ok = client.post(f"/api/cards/{c['id']}/edit", json={"base_version_id": c["current_version_id"], "op": "remove", "symbol_id": c["current_version"]["symbols_declared"][0]["symbol_id"], "bet_axis": 0, "rationale": "less", "n": 1}, headers=mate)
    assert ok.status_code in (200, 202), ok.text


def test_maker_can_open_early_after_one_reading(client):
    owner = guest(client, "solo")
    readers = [guest(client, f"r{i}") for i in range(3)]
    d = client.post("/api/decks", json={"name": "Big deck", "visibility": "public", "origin": {"kind": "base", "base_deck_id": "bd_smith1909"}, "structure_template_id": "majors22", "card_mode": "reference"}, headers=owner).json()
    for h in readers:  # three members → threshold stays 3
        inv = client.post(f"/api/decks/{d['id']}/invitations", json={"link": True, "role": "member"}, headers=owner).json()
        tok = inv.get("link_token") or inv.get("token") or (inv.get("accept_url") or "").split("/")[-2]
        client.post(f"/api/invitations/{tok}/accept", headers=h)
    c = make_card(client, owner, d["id"], "major-01")
    assert c["readings"]["threshold"] == 3 and c["can"]["open_for_edits"] is False
    assert client.post(f"/api/cards/{c['id']}/open", headers=owner).status_code == 409  # no reading yet
    client.post(f"/api/versions/{c['current_version_id']}/readings", json={"axes": [0] * 8}, headers=readers[0])
    c = client.get(f"/api/cards/{c['id']}", headers=owner).json()
    assert c["status"] == "reading" and c["can"]["open_for_edits"] is True
    assert client.post(f"/api/cards/{c['id']}/open", headers=readers[1]).status_code == 403  # not the maker, not a curator
    c = client.post(f"/api/cards/{c['id']}/open", headers=owner).json()
    assert c["status"] == "open"


def test_inherited_drafts_are_readable_and_open_once_the_intent_exists(client):
    owner, mate = guest(client, "own2"), guest(client, "mate2")
    d = client.post("/api/decks", json={"name": "Inherited pair", "visibility": "public", "origin": {"kind": "base", "base_deck_id": "bd_smith1909"}, "structure_template_id": "majors22", "card_mode": "inherit"}, headers=owner).json()
    inv = client.post(f"/api/decks/{d['id']}/invitations", json={"link": True, "role": "member"}, headers=owner).json()
    assert client.post(f"/api/invitations/{inv['link_token']}/accept", headers=mate).status_code in (200, 201)
    q = client.get(f"/api/decks/{d['id']}/read/next", headers=mate).json()
    assert not q["empty"] and q["intent_missing"] is True and q["status"] == "draft"  # drafts with an image can be read
    r = client.post(f"/api/versions/{q['version']['id']}/readings", json={"axes": [2, -1, 1, -2, 2, 2, 2, -3], "free_text": "a leap"}, headers=mate)
    assert r.status_code == 200, r.text
    assert r.json()["card_status"] == "draft" and r.json()["reveal"]["intent_xy"] is None and r.json()["reveal"]["card"]["intent_missing"] is True
    cid = q["card_id"]
    # the maker writes the intent → reading, and the reading gathered as a draft opens the card (threshold 1)
    c = client.patch(f"/api/cards/{cid}", json={"intent": {"statement": "a fresh start", "axes": [-2, -3, -1, 1, -1, -1, 0, -1]}}, headers=owner).json()
    assert c["status"] == "open", c["status"]
    g = client.get(f"/api/decks/{d['id']}/grammar", headers=owner).json()
    assert g["n_real"] == 1  # the draft reading trains the grammar

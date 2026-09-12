"""Slice 3: deck wizard (blank / base with inherit / fork), members, invitations, settings, and the §2.4 permission matrix."""
import pytest

from tests.v5util import guest, login, make_client, seed_base


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with make_client(tmp_path_factory.mktemp("s3")) as c:
        seed_base(c, n_cards=3)
        yield c


@pytest.fixture(scope="module")
def people(client):
    return {"owner": login(client, "owner@example.org", "Owner"), "curator": login(client, "curator@example.org", "Cur"),
            "member": login(client, "member@example.org", "Mem"), "reader": login(client, "reader@example.org", "Rdr"), "guest": guest(client, "gst")}


def test_structures(client):
    keys = {t["key"]: len(t["positions"]) for t in client.get("/api/structures").json()}
    assert keys["tarot78"] == 78 and keys["majors22"] == 22 and keys["minors56"] == 56 and keys["lenormand36"] == 36 and keys["mantegna50"] == 50 and keys["free"] == 0


def test_create_blank_deck(client, people):
    o = people["owner"]
    r = client.post("/api/decks", json={"name": "Blank deck", "visibility": "public", "structure_template_id": "free"}, headers=o["h"])
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["slug"] == "blank-deck" and d["your_role"] == "owner" and d["stats"]["cards"] == 0 and d["origin"]["kind"] == "blank"
    r2 = client.post("/api/decks", json={"name": "Blank deck"}, headers=o["h"]).json()
    assert r2["slug"] == "blank-deck-2"
    # guests cannot create decks
    assert client.post("/api/decks", json={"name": "x"}, headers=people["guest"]["h"]).status_code == 403
    assert client.post("/api/decks", json={"name": "x"}).status_code == 401


def test_create_from_base_inherit(client, people):
    o = people["owner"]
    body = {"name": "Smith remake", "visibility": "public", "origin": {"kind": "base", "base_deck_id": "bd_smith1909"}, "card_mode": "inherit"}
    d = client.post("/api/decks", json=body, headers=o["h"]).json()
    assert d["structure_template_id"] == "majors22" and d["stats"]["filled_positions"] == 3 and d["stats"]["total_positions"] == 22
    assert d["stats"]["symbols"] == 3 and d["style_guide"]["line"] == "ink" and len(d["style_guide"]["reference_images"]) == 3
    syms = client.get(f"/api/decks/{d['id']}/symbols").json()
    crown = next(s for s in syms if s["key"] == "crown")
    assert crown["origin"] == "inherited_base" and crown["prior_source"] == "attestation" and crown["prior_axes"] == [0, 0, 0, 0, -1, 0, -2, 0]
    from routers.deps import store
    cards = store().find("cards", deck_id=d["id"])
    assert len(cards) == 3 and all(c["status"] == "draft" for c in cards)
    v0 = store().get("versions", cards[0]["current_version_id"])
    assert v0["how"]["mode"] == "upload" and v0["how"]["provider"] == "base_deck" and v0["image_url"].endswith(".jpg")
    fool = next(c for c in cards if c["position_key"] == "major-00")
    vf = store().get("versions", fool["current_version_id"])
    assert [x["symbol_id"] for x in vf["symbols_declared"]] == [crown["id"]] and vf["symbols_detected"][0]["declared_only"] is True
    # reference-only mode fills nothing
    d2 = client.post("/api/decks", json={**body, "name": "Smith refs", "card_mode": "reference", "import_symbols": ["sun"]}, headers=o["h"]).json()
    assert d2["stats"]["cards"] == 0 and d2["stats"]["symbols"] == 1


@pytest.fixture(scope="module")
def deck(client, people):
    o = people["owner"]
    d = client.post("/api/decks", json={"name": "Matrix deck", "visibility": "private", "origin": {"kind": "base", "base_deck_id": "bd_smith1909"}}, headers=o["h"]).json()
    did = d["id"]
    assert client.post(f"/api/decks/{did}/members", json={"user_id": people["curator"]["user"]["id"], "role": "curator"}, headers=o["h"]).status_code == 201
    assert client.post(f"/api/decks/{did}/members", json={"user_id": people["member"]["user"]["id"], "role": "member"}, headers=o["h"]).status_code == 201
    return d


def test_members_and_roles(client, people, deck):
    did = deck["id"]
    members = client.get(f"/api/decks/{did}/members", headers=people["owner"]["h"]).json()
    assert [m["role"] for m in members] == ["owner", "curator", "member"] and members[0]["name"] == "Owner"
    # only the owner manages roles
    assert client.patch(f"/api/decks/{did}/members/{people['member']['user']['id']}", json={"role": "curator"}, headers=people["curator"]["h"]).status_code == 403
    assert client.patch(f"/api/decks/{did}/members/{people['member']['user']['id']}", json={"role": "curator"}, headers=people["owner"]["h"]).json()["role"] == "curator"
    assert client.patch(f"/api/decks/{did}/members/{people['member']['user']['id']}", json={"role": "member"}, headers=people["owner"]["h"]).json()["role"] == "member"
    # invitations: curators may invite; the link accepts once
    inv = client.post(f"/api/decks/{did}/invitations", json={"role": "member"}, headers=people["curator"]["h"]).json()
    assert client.post(f"/api/decks/{did}/invitations", json={"role": "member"}, headers=people["member"]["h"]).status_code == 403
    newcomer = login(client, "new@example.org")
    assert client.post(f"/api/invitations/{inv['link_token']}/accept", headers=newcomer["h"]).json()["role"] == "member"
    assert client.post(f"/api/invitations/{inv['link_token']}/accept", headers=newcomer["h"]).status_code == 404
    assert client.get(f"/api/decks/{did}", headers=newcomer["h"]).json()["your_role"] == "member"
    client.delete(f"/api/decks/{did}/members/{newcomer['user']['id']}", headers=people["owner"]["h"])
    assert client.get(f"/api/decks/{did}", headers=newcomer["h"]).status_code == 403


def test_permission_matrix_routes(client, people, deck):
    """Spec §2.4 over the deck routes of slices 3–4."""
    did = deck["id"]
    h = {k: v["h"] for k, v in people.items()}
    # view private deck: members+ only; guest/reader get 403
    for who, code in (("guest", 403), ("reader", 403), ("member", 200), ("curator", 200), ("owner", 200)):
        assert client.get(f"/api/decks/{did}", headers=h[who]).status_code == code, who
    assert client.get(f"/api/decks/{did}").status_code == 404
    # style guide: curator+; general settings and visibility: owner only
    for who, code in (("member", 403), ("curator", 200), ("owner", 200)):
        assert client.patch(f"/api/decks/{did}", json={"style_guide": {"line": "woodcut"}}, headers=h[who]).status_code == code, who
    for who, code in (("curator", 403), ("owner", 200)):
        assert client.patch(f"/api/decks/{did}", json={"visibility": "unlisted"}, headers=h[who]).status_code == code, who
    # unlisted → readers and guests can view
    assert client.get(f"/api/decks/{did}", headers=h["guest"]).status_code == 200
    # symbols: propose member+; add curator+
    draft = {"name": "Bridge", "gloss": "a bridge", "declared_axes": [0] * 8}
    for who, code in (("guest", 403), ("reader", 403), ("member", 201), ("curator", 201), ("owner", 201)):
        assert client.post(f"/api/decks/{did}/symbol-proposals", json={"symbol_draft": draft, "note": "please"}, headers=h[who]).status_code == code, who
    for who, code in (("member", 403), ("curator", 201), ("owner", 201)):
        assert client.post(f"/api/decks/{did}/symbols", json={**draft, "name": f"Bridge {who}"}, headers=h[who]).status_code == code, who
    # members: owner only; delete: owner only
    assert client.post(f"/api/decks/{did}/members", json={"user_id": people["reader"]["user"]["id"]}, headers=h["curator"]).status_code == 403
    assert client.delete(f"/api/decks/{did}", headers=h["curator"]).status_code == 403
    # fork: readers may fork a visible deck when allow_forks; guests never
    assert client.post(f"/api/decks/{did}/fork", json={"name": "Reader fork"}, headers=h["reader"]).status_code == 201
    assert client.post(f"/api/decks/{did}/fork", json={"name": "Guest fork"}, headers=h["guest"]).status_code == 403
    client.patch(f"/api/decks/{did}", json={"settings": {"allow_forks": False}}, headers=h["owner"])
    assert client.post(f"/api/decks/{did}/fork", json={"name": "No fork"}, headers=h["member"]).status_code == 403


def test_permission_matrix_functions(client, people, deck):
    """The predicate layer, role by role."""
    from models import Card, Deck, User
    from routers.deps import store
    from service import permissions as P

    s = store()
    d = Deck(**s.get("decks", deck["id"]))
    d.visibility = "private"
    users = {k: User(**s.get("users", v["user"]["id"])) for k, v in people.items()}
    assert [P.role_in_deck(s, d, users[k]) for k in ("owner", "curator", "member", "reader", "guest")] == ["owner", "curator", "member", "reader", "guest"]
    assert P.role_in_deck(s, d, None) == "none"
    assert [P.can_view(s, d, users[k]) for k in ("owner", "curator", "member", "reader", "guest")] == [True, True, True, False, False]
    d.visibility = "public"
    assert all(P.can_view(s, d, users[k]) for k in users) and P.can_view(s, d, None)
    assert [P.can_create_card(s, d, users[k]) for k in ("owner", "curator", "member", "reader")] == [True, True, True, False]
    d.settings.who_can_create_cards = "curators"
    assert P.can_create_card(s, d, users["member"]) is False
    assert [P.can_manage_symbols(s, d, users[k]) for k in ("owner", "curator", "member")] == [True, True, False]
    assert [P.can_propose_symbol(s, d, users[k]) for k in ("member", "reader", "guest")] == [True, False, False]
    assert [P.can_manage_members(s, d, users[k]) for k in ("owner", "curator")] == [True, False]
    assert [P.can_host_session(s, d, users[k]) for k in ("member", "reader", "guest")] == [True, False, False]
    assert [P.can_join_session_as_reader(s, d, users[k]) for k in ("reader", "guest")] == [True, True]
    d.settings.allow_guest_readers = False
    assert P.can_join_session_as_reader(s, d, users["guest"]) is False and P.can_read_card(s, d, users["guest"]) is False
    d.settings.allow_forks = True
    assert [P.can_fork(s, d, users[k]) for k in ("reader", "member", "guest")] == [True, True, False]
    d.settings.allow_forks = False
    assert P.can_fork(s, d, users["member"]) is False
    # editor resolution: makers approve people, never edits
    card = Card(id="c_x", deck_id=d.id, position_key="major-00", maker_id=users["owner"].id)
    d.settings.default_editor_policy = "any_member"
    assert [P.is_approved_editor(s, card, d, users[k]) for k in ("member", "curator", "reader")] == [True, True, False]
    d.settings.default_editor_policy = "curators"
    assert [P.is_approved_editor(s, card, d, users[k]) for k in ("member", "curator")] == [False, True]
    d.settings.default_editor_policy = "maker_list"
    assert P.is_approved_editor(s, card, d, users["curator"]) is False
    card.approved_editors = [users["member"].id]
    assert [P.is_approved_editor(s, card, d, users[k]) for k in ("member", "curator")] == [True, False]
    assert P.is_maker(card, users["owner"]) and not P.is_maker(card, users["member"])


def test_fork_copies_symbols_cards_and_lineage(client, people):
    o = people["owner"]
    src = client.post("/api/decks", json={"name": "Fork source", "visibility": "public", "origin": {"kind": "base", "base_deck_id": "bd_smith1909"}}, headers=o["h"]).json()
    f = client.post(f"/api/decks/{src['id']}/fork", json={"name": "My fork", "visibility": "public"}, headers=people["member"]["h"]).json()
    assert f["origin"]["kind"] == "fork" and f["origin"]["forked_from_deck_id"] == src["id"] and f["your_role"] == "owner"
    assert f["stats"]["cards"] == 3 and f["stats"]["symbols"] == 3
    syms = client.get(f"/api/decks/{f['id']}/symbols").json()
    assert all(s["origin"] == "inherited_fork" and s["inherited_from"]["deck_id"] == src["id"] and s["prior_axes"] for s in syms)
    lin = client.get(f"/api/decks/{f['id']}/lineage").json()
    assert lin["ancestors"][0]["deck_id"] == src["id"] and lin["base_deck"]["slug"] == "smith1909"
    assert client.get(f"/api/decks/{src['id']}/lineage").json()["children"][0]["deck_id"] == f["id"]
    from routers.deps import store
    v = store().find("versions", deck_id=f["id"])[0]
    assert v["base_version_id"] and v["v"] == 0
    assert store().count("readings", deck_id=f["id"]) == 0
    assert store().count("fork_snapshots", target_deck_id=f["id"]) == 1
    listed = client.get("/api/decks?visibility=public&sort=forks").json()
    assert listed[0]["id"] == src["id"] and listed[0]["stats"]["forks"] == 1
    act = client.get(f"/api/decks/{src['id']}/activity").json()
    assert any(a["kind"] == "deck.forked" for a in act)


def test_transfer_and_delete(client, people):
    o = people["owner"]
    d = client.post("/api/decks", json={"name": "Temp deck"}, headers=o["h"]).json()
    client.post(f"/api/decks/{d['id']}/members", json={"user_id": people["member"]["user"]["id"]}, headers=o["h"])
    r = client.patch(f"/api/decks/{d['id']}", json={"owner_id": people["member"]["user"]["id"]}, headers=o["h"]).json()
    assert r["owner_id"] == people["member"]["user"]["id"] and r["your_role"] == "curator"
    assert client.delete(f"/api/decks/{d['id']}", headers=o["h"]).status_code == 403
    assert client.delete(f"/api/decks/{d['id']}", headers=people["member"]["h"]).json()["deleted"] == d["id"]
    assert client.get(f"/api/decks/{d['id']}", headers=people["member"]["h"]).status_code == 404

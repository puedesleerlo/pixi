"""Slice 11/12: export ZIP + print PDF jobs, reports → moderation queue, admin endpoints gated."""
import io
import json
import os
import sys
import zipfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("PIXIE_EMBED", "hash")
os.environ["PIXIE_WORKER"] = "inline"
os.environ["PIXIE_ADMIN_EMAILS"] = "root@example.com"
os.environ["PIXIE_EXPORT_FETCH"] = "0"  # no network in tests: images are referenced by URL in the manifest


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["PIXIE_SNAPSHOT"] = str(tmp_path_factory.mktemp("state") / "state.json")
    import importlib
    import main as m

    importlib.reload(m)
    from fastapi.testclient import TestClient

    with TestClient(m.app) as c:
        yield c


def login(client, email):
    t = client.post("/api/auth/magic", json={"email": email}).json()["token"]
    r = client.get(f"/api/auth/magic/{t}", follow_redirects=False)
    tok = r.json()["token"] if r.headers.get("content-type", "").startswith("application/json") else None
    client.cookies.clear()
    if tok is None:
        tok = client.post("/api/auth/magic", json={"email": email}).json()["token"]
        r = client.get(f"/api/auth/magic/{tok}", follow_redirects=False)
        tok = r.json()["token"]
        client.cookies.clear()
    return {"Authorization": f"Bearer {tok}"}


def test_export_and_print(client):
    h = login(client, "owner@example.com")
    d = client.post("/api/decks", json={"name": "Export deck", "visibility": "public", "origin": {"kind": "base", "base_deck_id": "bd_smith1909"}, "card_mode": "inherit"}, headers=h).json()
    j = client.get(f"/api/decks/{d['id']}/export", headers=h).json()["job"]
    assert j["status"] == "done", j
    url = j["result"]["url"]
    data = client.get(url).content
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    assert {"manifest.json", "grammar.csv", "readings.csv", "README.txt"} <= set(names)
    man = json.loads(z.read("manifest.json"))
    assert len(man["cards"]) == 78 and all(c.get("image_url") for c in man["cards"])
    jp = client.get(f"/api/decks/{d['id']}/print", headers=h).json()["job"]
    assert jp["status"] == "done"
    pdf = client.get(jp["result"]["url"]).content
    assert pdf[:4] == b"%PDF" and len(pdf) > 10000
    # members only
    g = client.post("/api/auth/guest", json={"name": "g"}).json()["token"]
    assert client.get(f"/api/decks/{d['id']}/export", headers={"Authorization": f"Bearer {g}"}).status_code == 403


def test_reports_and_admin(client):
    h = login(client, "member@example.com")
    r = client.post("/api/reports", json={"kind": "deck", "ref_id": "d_playground", "reason": "test report"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "open"
    assert client.get("/api/admin/moderation", headers=h).status_code == 403
    a = login(client, "root@example.com")
    q = client.get("/api/admin/moderation", headers=a).json()
    assert any(x["ref_id"] == "d_playground" for x in q)
    rid = q[0]["id"]
    assert client.patch(f"/api/admin/moderation/{rid}?action=dismiss", headers=a).json()["status"] == "closed"
    hp = client.get("/api/admin/providers/health", headers=a).json()
    assert hp["image_provider"] == "local" and "keys" in hp
    m = client.get("/api/admin/metrics", headers=a).json()
    assert m["decks"] >= 2 and m["readings"] >= 620
    assert client.patch("/api/admin/quotas", json={"deck_id": "d_playground", "generation_quota_month": 5}, headers=a).json()["generation_quota_month"] == 5

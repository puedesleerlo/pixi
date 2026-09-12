"""Slice 1: auth (guest, magic link, upgrade, /me), storage, jobs + SSE, notifications, health."""
import pytest

from tests.v5util import guest, login, make_client


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    with make_client(tmp_path_factory.mktemp("s1")) as c:
        yield c


def test_health(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["store"] == "memory" and h["storage"] == "local" and h["worker"] == "inline"


def test_guest_and_me(client):
    g = guest(client, "ana")
    assert g["user"]["is_guest"] is True and g["user"]["name"] == "ana"
    me = client.get("/api/me", headers=g["h"]).json()
    assert me["user"]["id"] == g["user"]["id"]
    assert client.get("/api/me").json()["user"] is None
    # cookie path works too
    r = client.post("/api/auth/guest", json={"name": "bo"})
    assert "pixie_session" in r.cookies
    assert client.get("/api/me").json()["user"]["name"] == "bo"
    client.cookies.clear()


def test_magic_link_login_and_single_use(client):
    r = client.post("/api/auth/magic", json={"email": "Ana@Example.org", "name": "Ana"}).json()
    assert r["login_url"].endswith(f"/auth/magic/{r['token']}") and r["sent"] is False
    r2 = client.get(f"/api/auth/magic/{r['token']}").json()
    client.cookies.clear()
    assert r2["user"]["email"] == "ana@example.org" and r2["user"]["is_guest"] is False
    assert client.get(f"/api/auth/magic/{r['token']}").status_code == 400  # single use
    assert client.get("/api/me", headers={"Authorization": f"Bearer {r2['token']}"}).json()["user"]["name"] == "Ana"
    assert client.get("/api/me", headers={"Authorization": "Bearer u_x.9999999999.deadbeef"}).json()["user"] is None


def test_guest_upgrade_keeps_identity(client):
    g = guest(client, "cy")
    r = client.post("/api/auth/upgrade", json={"email": "cy@example.org"}, headers=g["h"]).json()
    assert r["user"]["id"] == g["user"]["id"] and r["user"]["is_guest"] is False
    assert client.get("/api/me", headers={"Authorization": f"Bearer {r['token']}"}).json()["user"]["email"] == "cy@example.org"


def test_jobs_inline_and_sse(client):
    u = login(client, "jobs@example.org")
    j = client.post("/api/jobs/test", json={"n": 4}, headers=u["h"]).json()
    assert j["status"] == "done" and j["progress"] == 1.0 and j["result"] == {"counted": 4}
    assert client.get(f"/api/jobs/{j['id']}", headers=u["h"]).json()["note"] == "step 4/4"
    with client.stream("GET", f"/api/jobs/{j['id']}/events", headers=u["h"]) as r:
        body = "".join(r.iter_text())
    assert "event: job.done" in body and '"counted": 4' in body
    # retries: fails twice then succeeds (3 attempts)
    j2 = client.post("/api/jobs/test", json={"n": 1, "fail_times": 2}, headers=u["h"]).json()
    assert j2["status"] == "done" and j2["attempts"] == 3
    j3 = client.post("/api/jobs/test", json={"n": 1, "fail_times": 5}, headers=u["h"]).json()
    assert j3["status"] == "failed" and "simulated" in j3["error"]
    # jobs are private to their creator
    other = login(client, "other@example.org")
    assert client.get(f"/api/jobs/{j['id']}", headers=other["h"]).status_code == 404
    assert client.get(f"/api/jobs/{j['id']}").status_code == 401


def test_storage_and_signed_media(client):
    from routers.deps import storage

    st = storage()
    key = st.put("decks/d_test/x.txt", b"hello", "text/plain")
    assert client.get(f"/media/{key}").text == "hello"
    pk = st.put("private/d_test/secret.txt", b"shh", "text/plain")
    assert client.get(f"/media/{pk}").status_code == 403
    url = st.url(pk)
    assert client.get(url).text == "shh"
    assert client.get(url.replace("sig=", "sig=0")).status_code == 403


def test_notifications(client):
    u = login(client, "notif@example.org")
    from routers.deps import store
    from service.notifications import notify

    n = notify(store(), u["user"]["id"], "test", "hello")
    r = client.get("/api/notifications", headers=u["h"]).json()
    assert r["unread"] == 1 and r["items"][0]["id"] == n["id"]
    assert client.patch(f"/api/notifications/{n['id']}", json={"read": True}, headers=u["h"]).json()["read_at"]
    assert client.get("/api/notifications", headers=u["h"]).json()["unread"] == 0
    stranger = login(client, "stranger@example.org")
    assert client.patch(f"/api/notifications/{n['id']}", json={"read": True}, headers=stranger["h"]).status_code == 404

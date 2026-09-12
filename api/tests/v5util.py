"""Shared helpers for the v5 API tests: an isolated app + memory store, users via the dev magic link."""
import importlib
import os

os.environ.setdefault("PIXIE_EMBED", "hash")
os.environ["PIXIE_WORKER"] = "inline"


def make_client(tmp_path):
    os.environ["PIXIE_SNAPSHOT"] = str(tmp_path / "state.json")
    os.environ["PIXIE_STORAGE_DIR"] = str(tmp_path / "storage")
    os.environ.pop("MONGODB_URI", None)
    os.environ.pop("S3_BUCKET", None)
    import storage as storage_mod
    importlib.reload(storage_mod)
    import main as m
    importlib.reload(m)
    from fastapi.testclient import TestClient

    return TestClient(m.app)


def login(client, email: str, name: str | None = None) -> dict:
    """Account via the dev magic link. Returns {"h": headers, "user": …}."""
    client.cookies.clear()
    r = client.post("/api/auth/magic", json={"email": email, "name": name or email.split("@")[0]})
    assert r.status_code == 200, r.text
    r2 = client.get(f"/api/auth/magic/{r.json()['token']}")
    assert r2.status_code == 200, r2.text
    tok = r2.json()["token"]
    client.cookies.clear()
    return {"h": {"Authorization": f"Bearer {tok}"}, "user": r2.json()["user"], "token": tok}


def guest(client, name="guest") -> dict:
    client.cookies.clear()
    r = client.post("/api/auth/guest", json={"name": name})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    return {"h": {"Authorization": f"Bearer {r.json()['token']}"}, "user": r.json()["user"], "token": r.json()["token"]}


def seed_base(client, slug="smith1909", n_cards=3, symbols=True):
    """Seed a tiny base deck straight into the store (B2's ingestion may not have run)."""
    from routers.deps import store

    s = store()
    bd = {"id": f"bd_{slug}", "slug": slug, "name": "Smith 1909", "tradition": "Waite-Smith line art", "year": 1909,
          "structure_template_id": "majors22", "card_count": n_cards, "status": "ready", "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}
    s.put("base_decks", bd)
    from service.decks import structure

    positions = structure("majors22").positions[:n_cards]
    for p in positions:
        s.put("base_cards", {"id": f"bc_{slug}_{p.key}", "base_deck_id": bd["id"], "position_key": p.key, "title": p.title,
                             "image_url": f"https://example.org/{slug}/{p.key}.jpg", "thumb_url": None, "caption": "Pamela Colman Smith, 1909 · public domain",
                             "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"})
    if symbols:
        for key, name, axes, cards in (("crown", "Crown", [0, 0, 0, 0, -1, 0, -2, 0], [positions[0].key]),
                                       ("sun", "Sun", [-2, -1, -1, 1, -2, -1, -2, 0], [positions[1].key] if n_cards > 1 else []),
                                       ("tower", "Tower", [1, 2, 1, 1, 2, 2, 2, 0], [])):
            s.put("base_symbols", {"id": f"bs_{slug}_{key}", "base_deck_id": bd["id"], "base_deck_slug": slug, "key": key, "name": name,
                                   "gloss": f"a {name.lower()}", "tags": [], "placement": "top" if key == "sun" else "any", "attested_axes": axes,
                                   "attestations": [{"source": "Waite 1911", "note": "test"}], "exemplar": {"image_url": None}, "cards": cards,
                                   "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"})
    return bd

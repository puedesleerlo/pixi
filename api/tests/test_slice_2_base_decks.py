"""Slice 2 — base decks: manifests, registries, ingestion, router. Independent of B1 (tiny app + MemoryStore)."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.dirname(HERE)
sys.path.insert(0, API)
DATA = os.path.normpath(os.path.join(API, "..", "data"))

from pixie.store import MemoryStore  # noqa: E402
from service import base_decks as svc  # noqa: E402


def test_structures_and_manifests_parse():
    st = {t["key"]: t for t in svc.load_structures(DATA)}
    assert {"tarot78", "majors22", "minors56", "lenormand36", "mantegna50", "free"} <= set(st)
    assert len(st["tarot78"]["positions"]) == 78 and st["tarot78"]["positions"][0]["key"] == "major-00"
    assert len(st["lenormand36"]["positions"]) == 36 and len(st["mantegna50"]["positions"]) == 50
    ms = svc.load_manifests(DATA)
    assert len(ms) >= 11
    for m in ms.values():
        for k in ("slug", "name", "year", "rights_note", "source_urls", "structure_template", "status", "rights_checklist", "cards"):
            assert k in m, (m["slug"], k)
        assert "Rider-Waite" not in open(os.path.join(DATA, "base_decks", m["slug"], "manifest.json")).read()
        for c in m["cards"]:
            assert c["image_url"].startswith("https://") and c["position_key"] and c["title"] and c["caption"]


def test_smith_is_ready_and_conver_partial():
    ms = svc.load_manifests(DATA)
    smith, conver = ms["smith1909"], ms["conver1760"]
    assert smith["status"] == "ready" and len(smith["cards"]) == 78
    keys = {c["position_key"] for c in smith["cards"]}
    assert "major-00" in keys and "pentacles-14" in keys and "cups-01" in keys
    assert conver["status"] == "partial" and len(conver["cards"]) == 24
    for m in ms.values():
        if m["status"] == "ready":
            c = m["rights_checklist"]
            assert all(c.get(k) for k in ("source_page", "license_text", "date", "reviewer")), m["slug"]


def test_registries():
    reg = svc.load_registry("smith1909", DATA)
    assert reg and reg["version"] == 1 and len(reg["symbols"]) >= 30
    keys = {s["key"] for s in reg["symbols"]}
    for k in ("crown", "sun", "moon", "star", "tower", "water_falling", "cup", "sword", "wheel", "lantern", "key", "rose", "throne", "serpent", "pentacle"):
        assert k in keys, k
    for s in reg["symbols"]:
        assert len(s["declared_axes"]) == 8 and len(s["prior_axes"]) == 8 and s["prior_source"] == "attestation"
        assert s["origin"] == "inherited_base" and s["status"] == "active" and s["attestations"]
        assert all(-3 <= v <= 3 for v in s["declared_axes"])
    with_img = [s for s in reg["symbols"] if s.get("exemplar") and s["exemplar"].get("image_url")]
    assert len(with_img) >= 40
    assert reg["symbols_by_card"]["major-17"][0]["key"] in keys and any(x["key"] == "star" for x in reg["symbols_by_card"]["major-17"])
    conv = svc.load_registry("conver1760", DATA)
    assert conv and len(conv["symbols"]) >= 30 and all(s["key"].startswith("m_") for s in conv["symbols"])
    assert set(reg["symbols_by_card"]) and set(conv["symbols_by_card"])  # 22 majors each
    assert len(keys & {s["key"] for s in conv["symbols"]}) == 0  # ids unique across registries


def test_ingest_into_memory_store():
    store = MemoryStore()
    res = svc.ingest(store, None, "smith1909", DATA)
    assert res["cards"] == 78 and res["symbols"] >= 30 and res["downloaded"] is False
    d = svc.get_base_deck(store, "smith1909")
    assert d["id"] == "bd_smith1909" and d["symbol_registry_id"] == "reg_smith1909" and d["card_count"] == 78 and d["status"] == "ready"
    cards = svc.base_cards(store, "smith1909")
    assert len(cards) == 78 and cards[0]["id"] == "bc_smith1909_major-00" and cards[0]["title"] == "The Fool"
    assert cards[22]["position_key"] == "wands-01"
    assert svc.symbols_for_position(store, "smith1909", "major-16") and any(x["key"] == "lightning" for x in svc.symbols_for_position(store, "smith1909", "major-16"))
    assert svc.ensure_ingested(store, DATA) and len(store.all("base_decks")) >= 11  # the rest, no downloads
    assert svc.ensure_ingested(store, DATA) == []  # idempotent
    # re-ingest keeps created_at
    created = d["created_at"]
    svc.ingest(store, None, "smith1909", DATA)
    assert svc.get_base_deck(store, "smith1909")["created_at"] == created


class _FakeStorage:
    def __init__(self):
        self.blobs = {}

    def put(self, key, data, content_type):
        self.blobs[key] = (content_type, len(data))
        return key

    def url(self, key, private=False):
        return f"/media/{key}"


@pytest.mark.skipif(os.environ.get("PIXIE_NET") != "1", reason="network download; set PIXIE_NET=1")
def test_ingest_with_storage_downloads_and_thumbs():
    store = MemoryStore()
    st = _FakeStorage()
    svc.ingest(store, st, "conver1760", DATA)
    c = svc.base_cards(store, "conver1760")[0]
    assert c["image_url"].startswith("/media/base/conver1760/") and c["thumb_url"].endswith(".webp") and c["width"] > 0


def test_router_with_tiny_app():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import base_decks as r

    store = MemoryStore()
    svc.ensure_ingested(store, DATA)
    r.set_store_getter(lambda: store)
    app = FastAPI()
    app.include_router(r.router)
    c = TestClient(app)
    decks = c.get("/api/base-decks").json()
    assert decks[0]["slug"] == "smith1909" and decks[0]["rights_checklist_complete"] is True and "rights_checklist" not in decks[0]
    assert {d["status"] for d in decks} == {"ready", "partial", "planned"}
    d = c.get("/api/base-decks/smith1909").json()
    assert d["n_symbols"] >= 30 and d["card_count"] == 78
    cards = c.get("/api/base-decks/smith1909/cards").json()
    assert len(cards) == 78 and cards[0]["caption"].startswith("Pamela Colman Smith")
    syms = c.get("/api/base-decks/smith1909/symbols").json()
    assert len(syms["symbols"]) >= 30 and "major-17" in syms["symbols_by_card"]
    pos = c.get("/api/base-decks/smith1909/symbols", params={"position_key": "major-19"}).json()
    assert any(x["key"] == "sun" for x in pos)
    assert c.get("/api/base-decks/nope").status_code == 404
    # admin ingest: guarded by auth.require_admin when B1's auth module exists (unauthenticated → 401/403)
    guard = r._admin_guard()
    if guard.__name__ != "<lambda>":
        assert c.post("/api/admin/base-decks/ingest", json={"slug": "conver1760"}).status_code in (401, 403)
    app.dependency_overrides[guard] = lambda: None
    res = c.post("/api/admin/base-decks/ingest", json={"slug": "conver1760"}).json()
    assert res["cards"] == 24
    assert c.post("/api/admin/base-decks/ingest", json={"slug": "nope"}).status_code == 404

"""The synthetic playground deck (spec §8.6): planted grammar W* = Smith registry priors, 60 cards, 300 readings,
40 paired edits, one planted polysemous and one planted noisy version. Created once at boot; everything is
flagged `synthetic: true`. Reuses the v4 generator and converts its output to v5 documents."""
from __future__ import annotations

import os
from typing import Any

import numpy as np

from pixie import relay as R
from pixie.data import load_libraries, placeable
from pixie.seeds import generate_seeds
from pixie.slots import SLOTS
from service import measure

DECK_ID = "d_playground"
SLUG = "playground-synthetic"
OP_MAP = {"add": "add", "remove": "remove", "swap": "replace", "move": "reposition"}


def _registry_elements(store, data_dir: str) -> tuple[list[dict], dict[str, dict]]:
    """Elements for the v4 generator (id, size_class, historical_prior) + v5 symbol drafts keyed by id.
    Prefers stream B2's Smith registry; falls back to the v4 library sheet."""
    reg = store.get("base_symbol_registries", "reg_smith1909")
    if reg and reg.get("symbols"):
        els, drafts = [], {}
        for s in reg["symbols"]:
            prior = s.get("prior_axes") or s.get("declared_axes")
            if not prior:
                continue
            key = s.get("key") or s.get("id")
            size = "large" if s.get("placement") == "center" else "small"
            els.append({"id": key, "size_class": size, "historical_prior": prior, "label": s.get("name", key)})
            drafts[key] = s
        if len(els) >= 10:
            return els, drafts
    _, elements = load_libraries(data_dir)
    els = [e for e in placeable(elements) if e.get("library_id") == "smith1909" and e.get("historical_prior")]
    drafts = {e["id"]: {"key": e["id"], "name": e.get("label"), "gloss": e.get("gloss"), "tags": [e.get("parent_id")], "declared_axes": e["historical_prior"],
                        "prior_axes": e["historical_prior"], "prior_source": "attestation", "placement": "center" if e.get("size_class") == "large" else "any",
                        "exemplar": {"image_url": e.get("image_url"), "origin": "base_crop"}, "attestations": e.get("attestations", [])} for e in els}
    return els, drafts


def ensure_playground(store, data_dir: str, embed_fn=None) -> dict:
    deck = store.get("decks", DECK_ID)
    if deck and store.count("versions", deck_id=DECK_ID) > 0 and store.count("readings", deck_id=DECK_ID) > 0:
        if store.get("pca", "pca") is None:
            _fit_pca(store)
        return deck
    for coll in ("cards", "versions", "readings", "symbols"):
        for d in store.find(coll, deck_id=DECK_ID):
            store.delete(coll, d["id"])
    els, drafts = _registry_elements(store, data_dir)
    now = R.iso(R.utcnow())
    deck = {"id": DECK_ID, "slug": SLUG, "name": "Playground · synthetic", "description": "Seeded from the Smith 1909 registry priors: the deck reads exactly as the tradition does at t = 0. Everything here is synthetic and drawn muted.",
            "owner_id": "u_system", "visibility": "public", "structure_template_id": "free",
            "style_guide": {"prompt_prefix": "black ink line art on cream paper", "palette": ["#f4efe6", "#141414"], "line": "ink", "reference_images": [], "border": {"style": "hairline", "color": "#141414"}, "aspect": "2.75x4.75"},
            "origin": {"kind": "base", "base_deck_id": "bd_smith1909"},
            "settings": {"who_can_create_cards": "curators", "default_editor_policy": "curators", "allow_branches": False, "allow_forks": True, "allow_guest_readers": True,
                         "ready_threshold": 3, "max_edits_per_card": 6, "candidates_per_generation": 2, "fidelity_threshold": 0.85, "style_threshold": 0.70,
                         "generation_quota_month": 0, "live_generation_in_sessions": False},
            "stats": {}, "lineage": {"ancestors": [], "children": []}, "synthetic": True, "created_at": now, "updated_at": now}
    store.put("decks", deck)
    if store.get("memberships", "m_playground_owner") is None:
        store.put("memberships", {"id": "m_playground_owner", "deck_id": DECK_ID, "user_id": "u_system", "role": "owner", "joined_at": now})
    sym_id = {key: f"sy_pg_{key}" for key in drafts}
    symbols = []
    for key, s in drafts.items():
        symbols.append({"id": sym_id[key], "deck_id": DECK_ID, "key": key, "name": s.get("name", key), "gloss": s.get("gloss", ""), "tags": s.get("tags", []),
                        "declared_axes": s.get("declared_axes") or s.get("prior_axes"), "declared_text": s.get("declared_text", ""),
                        "exemplar": s.get("exemplar") or {"image_url": None, "origin": "base_crop"}, "placement": s.get("placement", "any"),
                        "origin": "inherited_base", "inherited_from": {"base_deck_id": "bd_smith1909", "symbol_id": key}, "attestations": s.get("attestations", []),
                        "prior_axes": s.get("prior_axes") or s.get("declared_axes"), "prior_source": "attestation", "status": "active",
                        "measured": {"coef": [0.0] * 8, "ci_low": [0.0] * 8, "ci_high": [0.0] * 8, "n_cards": 0, "n_readings": 0, "n_edits": 0, "coherence": "untested", "declared_vs_measured": None},
                        "synthetic": True, "created_at": now, "updated_at": now})
    store.put_many("symbols", symbols)
    seeds = generate_seeds(els, n_cards=60, n_readings=300, n_edits=40, paired=4, noise_sd=0.8, seed=0, deck_id=DECK_ID)
    cards, versions, readings, planted = seeds["cards"], seeds["versions"], seeds["readings"], seeds["planted"]
    v_by_card: dict[str, list[dict]] = {}
    for v in versions:
        v_by_card.setdefault(v["card_id"], []).append(v)
    out_cards, out_versions = [], []
    for k, c in enumerate(sorted(cards, key=lambda c: c["id"])):
        vs = sorted(v_by_card.get(c["id"], []), key=lambda v: int(v["v"]))
        head = vs[-1]["id"] if vs else None
        out_cards.append({"id": c["id"], "deck_id": DECK_ID, "position_key": f"free-{k + 1:04d}", "title": None, "maker_id": "u_seed_maker",
                          "intent": {"statement": c["intent"]["statement"], "axes": c["intent"]["axes"], "embedding": None},
                          "approved_editors": "*", "edit_requests": [], "status": "closed", "current_version_id": head,
                          "branches": [{"branch_key": "main", "head_version_id": head}], "tags": [], "share_token": None,
                          "encoder_ids": ["u_seed_maker"], "synthetic": True, "created_at": now, "updated_at": now})
        prev_id = None
        for v in vs:
            detected = [{"symbol_id": sym_id[x["element_id"]], "salience": float(SLOTS.get(x["slot"], 0.6)), "bbox": None, "tagged_by": "human"}
                        for x in v.get("elements", []) if x["element_id"] in sym_id]
            declared = [{"symbol_id": d["symbol_id"], "placement": None} for d in detected]
            e = v.get("edit")
            if e:
                how = {"op": OP_MAP.get(e.get("type"), "add"), "symbol_id": sym_id.get(e.get("element_id")), "to_symbol_id": sym_id.get(e.get("to_element_id")),
                       "region": None, "prompt_user": None, "prompt_full": "(synthetic)", "provider": "seed", "model": "seed", "seed": 0, "candidates": [],
                       "chosen_index": 0, "bet_axis": e.get("bet_axis"), "rationale": e.get("rationale"), "editor_id": "u_seed_editor", "counts_as_experiment": True}
            else:
                how = {"mode": "upload", "reference_image_url": None, "prompt_user": None, "prompt_full": "(synthetic)", "provider": "seed", "model": "seed",
                       "seed": 0, "candidates": [], "chosen_index": 0}
            out_versions.append({"id": v["id"], "card_id": c["id"], "deck_id": DECK_ID, "v": int(v["v"]), "branch_key": "main", "base_version_id": prev_id,
                                 "image_url": None, "thumb_url": None, "width": None, "height": None, "symbols_declared": declared, "symbols_detected": detected,
                                 "how": how, "checks": {"style_score": 1.0, "symbols_missing": [], "safety": "ok"}, "created_by": "u_seed_maker" if not e else "u_seed_editor",
                                 "synthetic": True, "created_at": now})
            prev_id = v["id"]
    out_readings = [{"id": r["id"], "deck_id": DECK_ID, "card_id": r["card_id"], "version_id": r["version_id"], "reader_id": r.get("reader_id"),
                     "nickname": r.get("nickname"), "session_id": None, "round_id": None, "free_text": r.get("free_text"), "axes": r["axes"], "embedding": None,
                     "latency_ms": None, "synthetic": True, "created_at": now} for r in readings]
    if embed_fn is not None:
        try:
            vecs = embed_fn([c["intent"]["statement"] for c in out_cards])
            for c, vec in zip(out_cards, vecs):
                c["intent"]["embedding"] = [float(x) for x in vec]
        except Exception as e:  # embeddings are optional for seeds
            print(f"[seeds] embedding skipped: {e}")
    store.put_many("cards", out_cards)
    store.put_many("versions", out_versions)
    store.put_many("readings", out_readings)
    planted = {**planted, "polysemous_card_id": planted.get("polysemous_card_id"), "noisy_card_id": planted.get("noisy_card_id"),
               "W_star": {sym_id.get(k, k): v for k, v in (planted.get("W_star") or {}).items()}}
    store.put("meta", {"id": "seeds", "deck_id": DECK_ID, "planted": planted, "n_cards": len(out_cards), "n_versions": len(out_versions), "n_readings": len(out_readings)})
    _fit_pca(store)
    measure.invalidate(DECK_ID)
    print(f"[seeds] playground: {len(out_cards)} cards, {len(out_versions)} versions, {len(out_readings)} synthetic readings, {len(symbols)} symbols")
    return deck


def _fit_pca(store) -> None:
    cards = store.find("cards", deck_id=DECK_ID)
    rs = store.find("readings", deck_id=DECK_ID)
    pts = np.array([c["intent"]["axes"] for c in cards] + [r["axes"] for r in rs], dtype=float)
    if len(pts) >= 3:
        store.delete("pca", "pca")
        measure.ensure_pca(store, pts)


def planted(store) -> dict | None:
    return (store.get("meta", "seeds") or {}).get("planted")


def on_startup(state: dict) -> None:
    """main.py startup hook: create the synthetic playground deck once (spec §8.6)."""
    data_dir = os.environ.get("PIXIE_DATA_DIR") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "data")
    embed_fn = None
    try:
        from pixie.embed import embed as embed_fn  # noqa: F811
    except Exception:
        pass
    ensure_playground(state["store"], data_dir, embed_fn)
    render_in_background(state)


def render_playground_images(store, storage, deck_id: str = DECK_ID, limit: int | None = None) -> int:
    """Give every playground version a real composed image via the local collage provider (spec §8.6 says the
    synthetic deck exists at deploy; images make it demoable). Idempotent; safe in a background thread."""
    try:
        from pixie.imaging.providers.local import LocalCollageProvider
    except Exception as e:
        print(f"[seeds] no local provider: {e}")
        return 0
    api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    syms = {s["id"]: s for s in store.find("symbols", deck_id=deck_id)}
    deck = store.get("decks", deck_id) or {}
    prov = LocalCollageProvider()
    n = 0
    versions = [v for v in store.find("versions", deck_id=deck_id) if not v.get("image_url")]
    versions.sort(key=lambda v: (v["card_id"], int(v.get("v", 0))))
    for v in versions[: limit or len(versions)]:
        exemplars = []
        for d in v.get("symbols_detected") or []:
            s = syms.get(d["symbol_id"])
            url = ((s or {}).get("exemplar") or {}).get("image_url")
            if not url or not url.startswith("/static/"):
                continue
            path = os.path.join(api_dir, url.lstrip("/"))
            if not os.path.exists(path):
                continue
            sal = float(d.get("salience", 0.6))
            placement = "center" if sal >= 0.95 else "top" if sal >= 0.75 and not any(e.get("placement") == "top" for e in exemplars) else "bottom" if sal >= 0.6 and not any(e.get("placement") == "bottom" for e in exemplars) else "left" if not any(e.get("placement") == "left" for e in exemplars) else "right"
            exemplars.append({"symbol_id": d["symbol_id"], "name": (s or {}).get("name"), "path": path, "placement": placement})
        try:
            res = prov.generate("(synthetic)", [], "2.75x4.75", 1, seed=abs(hash(v["id"])) % 10000, style_guide=deck.get("style_guide") or {}, symbol_exemplars=exemplars[:5])
            img = res.images[0]
            key = storage.put(f"decks/{deck_id}/{v['id']}.png", img, "image/png")
            v["image_url"] = storage.url(key)
            v["thumb_url"] = v["image_url"]
            v["width"], v["height"] = 550, 950
            store.put("versions", v)
            n += 1
        except Exception as e:
            print(f"[seeds] render failed for {v['id']}: {type(e).__name__}: {e}")
            break
    if n:
        print(f"[seeds] rendered {n} playground images")
    return n


def render_in_background(state: dict) -> None:
    import threading

    if state.get("storage") is None:
        return
    threading.Thread(target=render_playground_images, args=(state["store"], state["storage"]), daemon=True).start()

"""Service facade (v4): libraries + decks + relay → the payloads the routes return.

Everything derived (distances, gaps, paired shifts, grammar, verdicts, chains) is computed here on
read. No LLM touches a score, a bet, or a landing. K2 may only *name* (pixie.naming) and every label
says who produced it.
"""
from __future__ import annotations

import os
import threading
from typing import Any

import numpy as np

from pixie import relay as R
from pixie.axes import AXES, axes_to_words
from pixie.data import load_libraries, placeable
from pixie.effects import edit_effects
from pixie.embed import backend_name as embed_backend, embed
from pixie.geometry import FrozenPCA
from pixie.grammar import fit_grammar, historical_support
from pixie.metrics import LANDING_F, bet_hit, d_total, fidelity, gaps, landed as is_landed, maker_score, paired_shift
from pixie.naming import name_cluster
from pixie.seeds import generate_seeds
from pixie.slots import SLOTS, apply_move, validate_version
from pixie.verdict import polysemy_verdict

DEFAULT_CONFIG = {"w_axes": 0.6, "w_embed": 0.4, "radius": 0.30, "v_lo": 0.30, "alpha": 1.0, "w_synthetic": 0.25}
N_BOOT = int(os.environ.get("PIXIE_N_BOOT", "200"))
# Image URLs are relative by default ("/static/…") so the web app prefixes them with whatever host it
# reached the API on (a phone on the LAN cannot resolve the laptop's localhost). Set PIXIE_PUBLIC_URL to
# force absolute URLs, e.g. behind a CDN.
PUBLIC_URL = os.environ.get("PIXIE_PUBLIC_URL", "").rstrip("/")
PLAYGROUND_CODE = "PLAY"


def _f(x) -> float:
    return float(x)


def _list(a) -> list:
    return [float(v) for v in np.asarray(a, dtype=float).ravel()]


def edited_element_of(edit: dict | None) -> str | None:
    if not edit:
        return None
    return edit.get("to_element_id") if edit.get("type") == "swap" else edit.get("element_id")


class Engine:
    def __init__(self, data_dir: str, store):
        self.store = store
        self.data_dir = data_dir
        self.libraries, self.elements = load_libraries(data_dir)
        self.elem_by_id: dict[str, dict] = {e["id"]: e for e in self.elements}
        store.put_many("libraries", [{**l} for l in self.libraries])
        store.put_many("elements", [{**e} for e in self.elements])
        # generated / community elements live only in the store; merge them in
        for e in store.all("elements"):
            self.elem_by_id.setdefault(e["id"], e)
        self.config = {**DEFAULT_CONFIG, **(store.get("config", "config") or {})}
        self.config.pop("id", None)
        self._lock = threading.RLock()
        self._grammar_cache: dict[tuple, dict] = {}
        self._name_cache: dict[tuple, dict] = {}
        self.pca: FrozenPCA | None = None
        pca_doc = store.get("pca", "pca")
        if pca_doc:
            self.pca = FrozenPCA.from_dict(pca_doc)
        self.planted = (store.get("meta", "seeds") or {}).get("planted")
        self.playground = self.ensure_playground()
        self.ensure_seeds()
        threading.Thread(target=self._warm, daemon=True).start()

    # ------------------------------------------------------------------ setup
    def _warm(self):
        try:
            embed(["warm up"])
            print(f"[engine] embeddings ready ({embed_backend()})")
        except Exception as e:
            print(f"[engine] embedding warm-up failed: {e}")

    def ensure_playground(self) -> dict:
        deck = self.store.get("decks", PLAYGROUND_CODE)
        if deck is None:
            deck = self.new_deck("Playground", ["smith1909"], owner_id="g_system", nickname="system", code=PLAYGROUND_CODE)
            print("[engine] created the Playground deck")
        return deck

    def new_deck(self, name: str, libraries: list[str], owner_id: str, nickname: str, code: str | None = None) -> dict:
        code = code or R.new_code(self.store, "decks")
        known = {l["id"] for l in self.libraries}
        libs = [l for l in libraries if l in known] or ["smith1909"]
        community = f"community_{code.lower()}"
        self.store.put("libraries", {"id": community, "name": f"{name} · community", "kind": "community", "deck_id": code})
        deck = {"id": code, "code": code, "name": name.strip()[:40] or "deck", "owner_id": owner_id,
                "libraries": libs + [community], "community_library_id": community,
                "members": [{"guest_id": owner_id, "nickname": nickname, "joined_at": R.iso(R.utcnow())}],
                "open_read": True, "max_edits": 3 if code == PLAYGROUND_CODE else 6, "ready_threshold": 3,
                "created_at": R.iso(R.utcnow())}
        self.store.put("decks", deck)
        return deck

    def ensure_seeds(self) -> None:
        """§6.7: planted grammar = historical priors of the Smith library, in the Playground deck."""
        have = (self.store.count("readings", synthetic=True), self.store.count("versions", synthetic=True), self.store.count("cards", synthetic=True))
        if all(have) and self.pca is not None:
            return
        if any(have):  # a partial snapshot (e.g. readings without versions) — reseed cleanly
            print(f"[engine] partial seed state {have}; reseeding")
            for coll in ("readings", "versions", "cards"):
                for d in self.store.find(coll, synthetic=True):
                    self.store.delete(coll, d["id"])
        deck = self.playground
        elems = [e for e in self.deck_elements(deck) if e.get("library_id") == "smith1909"]
        seeds = generate_seeds(elems, n_cards=60, n_readings=300, n_edits=40, paired=4, noise_sd=0.8, seed=0, deck_id=deck["id"])
        cards, versions, readings, planted = seeds["cards"], seeds["versions"], seeds["readings"], seeds["planted"]
        for c in cards:
            c["deck_id"] = deck["id"]
            c.setdefault("maker_nickname", "seed maker")
            c.setdefault("intent", {}).setdefault("embedding", None)
        for v in versions:
            v["deck_id"] = deck["id"]
        for r in readings:
            r["deck_id"] = deck["id"]
        try:
            vecs = embed([c["intent"]["statement"] for c in cards])
            for c, vec in zip(cards, vecs):
                c["intent"]["embedding"] = _list(vec)
            texts = [(k, r["free_text"]) for k, r in enumerate(readings) if r.get("free_text")]
            if texts:
                vecs = embed([t for _, t in texts])
                for (k, _), vec in zip(texts, vecs):
                    readings[k]["embedding"] = _list(vec)
        except Exception as e:
            print(f"[engine] seed embedding skipped: {e}")
        self.store.put_many("cards", cards)
        self.store.put_many("versions", versions)
        self.store.put_many("readings", readings)
        pts = np.array([c["intent"]["axes"] for c in cards] + [r["axes"] for r in readings], dtype=float)
        self.pca = FrozenPCA().fit(pts)
        self.store.put("pca", {"id": "pca", **self.pca.to_dict()})
        seed_median = _f(planted.get("V_lo", 0.30))
        planted["seed_V_median"] = seed_median
        self.config["v_lo"] = max(0.30, seed_median)  # §6.4: 0.30 to start; the seed median is a noise floor
        self.save_config()
        self.planted = planted
        self.store.put("meta", {"id": "seeds", "planted": planted, "n_cards": len(cards), "n_versions": len(versions), "n_readings": len(readings)})
        self._grammar_cache.clear()
        print(f"[engine] seeded {len(cards)} cards, {len(versions)} versions, {len(readings)} synthetic readings")

    def save_config(self) -> None:
        self.store.put("config", {"id": "config", **self.config})
        self._grammar_cache.clear()

    def cfg(self) -> dict:
        return dict(self.config)

    # ------------------------------------------------------------------ elements & decks
    def abs_url(self, url: str | None) -> str | None:
        if not url:
            return None
        return url if url.startswith("http") or not PUBLIC_URL else PUBLIC_URL + url

    def element_view(self, eid: str, slot: str | None = None) -> dict:
        e = self.elem_by_id.get(eid, {"id": eid, "label": eid})
        out = {"id": eid, "element_id": eid, "label": e.get("label", eid), "image_url": self.abs_url(e.get("image_url")),
               "origin": e.get("origin", "tile"), "size_class": e.get("size_class"), "caption": e.get("caption"),
               "library_id": e.get("library_id"), "parent_id": e.get("parent_id"), "gloss": e.get("gloss")}
        if slot:
            out["slot"] = slot
            out["salience"] = SLOTS.get(slot, 0.0)
        return out

    def version_elements_view(self, version: dict) -> list[dict]:
        return [self.element_view(x["element_id"], x["slot"]) for x in version.get("elements", [])]

    def deck(self, code: str) -> dict:
        d = self.store.get("decks", code.upper())
        if d is None:
            raise KeyError(code)
        return d

    def deck_elements(self, deck: dict) -> list[dict]:
        libs = set(deck.get("libraries", []))
        out = [e for e in self.elem_by_id.values() if e.get("library_id") in libs and e.get("size_class")]
        for e in self.store.find("elements", library_id=deck.get("community_library_id")):
            if e["id"] not in self.elem_by_id:
                self.elem_by_id[e["id"]] = e
                if e.get("size_class"):
                    out.append(e)
        return sorted(out, key=lambda e: (e.get("library_id", ""), e["id"]))

    def deck_leaf_ids(self, deck: dict) -> list[str]:
        return [e["id"] for e in self.deck_elements(deck)]

    def picker(self, deck: dict) -> dict:
        groups: dict[str, list] = {}
        for e in self.deck_elements(deck):
            groups.setdefault(e.get("library_id", "?"), []).append(self.element_view(e["id"]))
        libs = {l["id"]: l for l in self.store.all("libraries")}
        return {"deck": self.deck_summary(deck),
                "libraries": [{"id": k, "name": libs.get(k, {}).get("name", k), "library": libs.get(k, {"id": k}), "elements": v} for k, v in groups.items()]}

    def deck_summary(self, deck: dict) -> dict:
        return {"id": deck["id"], "code": deck["code"], "name": deck["name"], "libraries": deck["libraries"],
                "n_members": len(deck.get("members", [])), "n_cards": self.store.count("cards", deck_id=deck["id"]),
                "open_read": deck.get("open_read", True), "max_edits": deck.get("max_edits", 3),
                "ready_threshold": deck.get("ready_threshold", 3), "owner_id": deck.get("owner_id")}

    def join_deck(self, deck: dict, guest_id: str, nickname: str) -> dict:
        for m in deck["members"]:
            if m["guest_id"] == guest_id:
                m["nickname"] = nickname or m["nickname"]
                break
        else:
            deck["members"].append({"guest_id": guest_id, "nickname": nickname, "joined_at": R.iso(R.utcnow())})
        self.store.put("decks", deck)
        return deck

    # ------------------------------------------------------------------ readings / versions
    def readings(self, deck_id: str | None = None, include_synthetic: bool = True, version_id: str | None = None,
                 exclude_round_id: str | None = None) -> list[dict]:
        if version_id:
            rs = self.store.find("readings", version_id=version_id)
        elif deck_id:
            rs = self.store.find("readings", deck_id=deck_id)
        else:
            rs = self.store.all("readings")
        if not include_synthetic:
            rs = [r for r in rs if not r.get("synthetic")]
        if exclude_round_id:
            rs = [r for r in rs if r.get("round_id") != exclude_round_id]
        rs.sort(key=lambda r: r.get("created_at") or "")
        return rs

    def versions_of_deck(self, deck_id: str) -> dict[str, dict]:
        return {v["id"]: v for v in self.store.find("versions", deck_id=deck_id)}

    def versions_of_card(self, card_id: str) -> list[dict]:
        vs = self.store.find("versions", card_id=card_id)
        vs.sort(key=lambda v: int(v["v"]))
        return vs

    def counts(self) -> dict:
        n_syn = self.store.count("readings", synthetic=True)
        n_all = self.store.count("readings")
        return {"n_readings": n_all, "n_real": n_all - n_syn, "n_synthetic": n_syn,
                "n_decks": self.store.count("decks"), "n_cards": self.store.count("cards"),
                "n_libraries": self.store.count("libraries"), "n_elements": len([e for e in self.elem_by_id.values() if e.get("size_class")])}

    def embed_text(self, text: str | None) -> list[float] | None:
        text = (text or "").strip()
        if not text:
            return None
        try:
            return _list(embed([text])[0])
        except Exception as e:
            print(f"[engine] embed failed: {e}")
            return None

    def distance(self, intent: dict, reading: dict) -> dict:
        return d_total(intent["axes"], reading["axes"], intent.get("embedding"), reading.get("embedding"), cfg=self.cfg())

    # ------------------------------------------------------------------ grammar (§6.5, per deck)
    def grammar(self, deck: dict, include_synthetic: bool = True, exclude_round_id: str | None = None) -> dict:
        rs = self.readings(deck_id=deck["id"], include_synthetic=include_synthetic, exclude_round_id=exclude_round_id)
        leaf_ids = self.deck_leaf_ids(deck)
        key = (deck["id"], len(rs), include_synthetic, exclude_round_id, self.config["alpha"], self.config.get("w_synthetic", 1.0), len(leaf_ids))
        with self._lock:
            if key in self._grammar_cache:
                return self._grammar_cache[key]
        pos = {eid: j for j, eid in enumerate(leaf_ids)}
        E = len(leaf_ids)
        versions = self.versions_of_deck(deck["id"])
        X_rows, Y_rows, used = [], [], []
        for r in rs:
            v = versions.get(r["version_id"])
            if v is None:
                continue
            row = np.zeros(E)
            for x in v.get("elements", []):
                j = pos.get(x["element_id"])
                if j is not None:
                    row[j] = SLOTS.get(x["slot"], 0.0)
            X_rows.append(row)
            Y_rows.append(r["axes"])
            used.append(r)
        if len(X_rows) < 3 or E == 0:
            fit = {"coef": np.zeros((E, 8)), "ci_low": np.zeros((E, 8)), "ci_high": np.zeros((E, 8)), "n": len(X_rows)}
        else:
            w_syn = float(self.config.get("w_synthetic", 1.0))
            weights = [w_syn if r.get("synthetic") else 1.0 for r in used]
            fit = fit_grammar(np.array(X_rows), np.array(Y_rows, dtype=float), alpha=float(self.config["alpha"]), n_boot=N_BOOT, seed=0,
                              sample_weight=weights if w_syn != 1.0 else None)
        coef, lo, hi = np.asarray(fit["coef"]), np.asarray(fit["ci_low"]), np.asarray(fit["ci_high"])
        try:
            effects = edit_effects(list(versions.values()), used)
        except Exception as e:
            print(f"[engine] edit_effects failed: {e}")
            effects = {}
        elements = []
        for j, eid in enumerate(leaf_ids):
            e = self.elem_by_id[eid]
            prior = e.get("historical_prior")
            eff = effects.get(eid) or {}
            elements.append({
                "element_id": eid, "library_id": e.get("library_id"), "label": e["label"], "parent_id": e.get("parent_id"),
                "origin": e.get("origin", "tile"), "gloss": e.get("gloss"), "image_url": self.abs_url(e.get("image_url")),
                "coef": _list(coef[j]) if E else [], "ci_low": _list(lo[j]) if E else [], "ci_high": _list(hi[j]) if E else [],
                "n": int(fit["n"]), "n_edits": int(eff.get("n_edits", 0)),
                "mean_effect": _list(eff["mean_effect"]) if eff.get("mean_effect") is not None else None,
                "historical_prior": _list(prior) if prior else None,
                "historical_support": _f(historical_support(coef[j], prior)) if prior else None,
                "attestations": e.get("attestations", []),
            })
        n_syn = sum(1 for r in used if r.get("synthetic"))
        n_edits = sum(1 for v in versions.values() if v.get("edit"))
        out = {"deck": self.deck_summary(deck), "axes": [list(a) for a in AXES], "n_readings": len(used), "n_real": len(used) - n_syn,
               "n_synthetic": n_syn, "n_edits": n_edits, "alpha": self.config["alpha"], "n_boot": N_BOOT, "w_synthetic": self.config.get("w_synthetic", 1.0),
               "elements": elements, "by_id": {x["element_id"]: x for x in elements}}
        with self._lock:
            self._grammar_cache[key] = out
        return out

    def grammar_strip(self, deck: dict, version: dict, exclude_round_id: str | None = None) -> list[dict]:
        g = self.grammar(deck, True, exclude_round_id)["by_id"]
        strip = []
        for x in version.get("elements", []):
            row = g.get(x["element_id"])
            if row is None:
                continue
            strip.append({"element_id": x["element_id"], "label": row["label"], "slot": x["slot"], "salience": SLOTS.get(x["slot"], 0.0),
                          "coef": row["coef"], "ci_low": row["ci_low"], "ci_high": row["ci_high"], "n": row["n"], "n_edits": row["n_edits"],
                          "historical_support": row["historical_support"], "origin": row["origin"]})
        return strip

    def bandwidth(self, deck: dict) -> list[dict]:
        real = self.readings(deck_id=deck["id"], include_synthetic=False)
        versions = self.versions_of_deck(deck["id"])
        cards: dict[str, dict] = {}
        by_version: dict[str, list[float]] = {}
        for r in real:
            card = cards.get(r["card_id"]) or self.store.get("cards", r["card_id"])
            if card is None:
                continue
            cards[r["card_id"]] = card
            by_version.setdefault(r["version_id"], []).append(self.distance(card["intent"], r)["d_total"])
        buckets: dict[int, list[float]] = {}
        for vid, ds in by_version.items():
            v = versions.get(vid)
            if v is None:
                continue
            buckets.setdefault(len(v.get("elements", [])), []).append(fidelity(ds))
        return [{"n_elements": k, "mean_fidelity": _f(np.mean(v)), "n_cards": len(v)} for k, v in sorted(buckets.items())]

    # ------------------------------------------------------------------ verdict (§6.4 + §6.6)
    def verdict(self, deck: dict, version: dict) -> dict:
        rs = self.readings(version_id=version["id"])
        n_syn = sum(1 for r in rs if r.get("synthetic"))
        base = {"version_id": version["id"], "card_id": version["card_id"], "n_real": len(rs) - n_syn, "n_synthetic": n_syn}
        if len(rs) < 8:
            return {**base, "verdict": "collecting", "n": len(rs), "needed": 8}
        axes = np.array([r["axes"] for r in rs], dtype=float)
        v = {**base, **polysemy_verdict(axes, v_lo=float(self.config["v_lo"]), n_null=200, seed=0, cfg=self.cfg())}
        if v.get("verdict") == "polysemous":
            g = self.grammar(deck)["by_id"]
            tops = sorted(((SLOTS.get(x["slot"], 0) * float(np.linalg.norm(g[x["element_id"]]["coef"])), g[x["element_id"]]["label"])
                           for x in version.get("elements", []) if x["element_id"] in g), reverse=True)[:2]
            for ci, cl in enumerate(v.get("clusters", [])):
                texts = [rs[i].get("free_text") for i in cl.get("member_idx", []) if rs[i].get("free_text")]
                key = (version["id"], len(rs), ci)
                if key not in self._name_cache:
                    self._name_cache[key] = name_cluster(texts, np.asarray(cl["centroid"]), [t[1] for t in tops])
                cl["label"] = self._name_cache[key]["label"]
                cl["label_by"] = self._name_cache[key]["by"]
        card_id = version["card_id"]
        v["planted"] = ("polysemous" if card_id == (self.planted or {}).get("polysemous_card_id")
                        else "noisy" if card_id == (self.planted or {}).get("noisy_card_id") else None)
        return v

    # ------------------------------------------------------------------ composing & editing
    def make_card(self, deck: dict, guest_id: str, body: dict, mode: str = "room") -> tuple[dict, dict]:
        valid = {e["id"]: e for e in self.deck_elements(deck)}
        elements = [{"element_id": x["element_id"], "slot": x["slot"]} for x in body.get("elements", [])]
        validate_version(elements, valid)  # raises ValueError
        statement = (body.get("statement") or "").strip()[:140]
        if not statement:
            raise ValueError("write what the card means (≤ 140 characters)")
        now = R.iso(R.utcnow())
        cid, vid = R.new_id("c_"), R.new_id("v_")
        card = {"id": cid, "deck_id": deck["id"], "mode": mode, "room_id": None, "maker_id": guest_id, "maker_nickname": None,
                "intent": {"statement": statement, "axes": [float(a) for a in body["axes"]], "embedding": self.embed_text(statement)},
                "approved_editors": body.get("approved_editors") or "*", "edit_requests": [], "status": "reading", "title": None,
                "title_by": None, "latest_version_id": vid, "n_versions": 1, "encoder_ids": [guest_id], "created_at": now,
                "finished_at": None, "synthetic": False}
        version = {"id": vid, "card_id": cid, "deck_id": deck["id"], "v": 0, "elements": elements, "edit": None, "created_at": now, "synthetic": False}
        return card, version

    def make_edit(self, deck: dict, card: dict, current: dict, guest_id: str, body: dict) -> dict:
        valid = {e["id"]: e for e in self.deck_elements(deck)}
        move = {k: body.get(k) for k in ("type", "element_id", "to_element_id", "to_slot")}
        new_elements = apply_move(current["elements"], move, valid)  # raises ValueError
        bet = int(body["bet_axis"])
        if not 0 <= bet <= 7:
            raise ValueError("bet_axis must be 0..7")
        return {"id": R.new_id("v_"), "card_id": card["id"], "deck_id": deck["id"], "v": int(current["v"]) + 1,
                "elements": [{"element_id": x["element_id"], "slot": x["slot"]} for x in new_elements],
                "edit": {**{k: v for k, v in move.items() if v is not None}, "editor_id": guest_id, "editor_nickname": None,
                         "bet_axis": bet, "rationale": (body.get("rationale") or "").strip()[:140] or None},
                "created_at": R.iso(R.utcnow()), "synthetic": False}

    def make_reading(self, guest_id: str, body: dict) -> dict:
        text = (body.get("free_text") or "").strip()[:140] or None
        return {"id": R.new_id("r_"), "reader_id": guest_id, "free_text": text, "axes": [float(a) for a in body["axes"]],
                "embedding": self.embed_text(text), "latency_ms": body.get("latency_ms"), "synthetic": False, "model": False,
                "created_at": R.iso(R.utcnow())}

    # ------------------------------------------------------------------ round readings & results
    def round_readings(self, rnd: dict, version_id: str | None = None) -> list[dict]:
        if rnd.get("replay"):
            step = rnd.get("replay_step", 0)
            if version_id and version_id != rnd["version_id"]:
                for k in range(step):
                    ver = rnd["replay_versions"][k]
                    if ver["version_id"] == version_id:
                        return ver.get("readings") or []
                return []
            return R.arrived_replay_readings(rnd)
        vid = version_id or rnd["version_id"]
        rs = self.store.find("readings", round_id=rnd["round_id"], version_id=vid)
        rs.sort(key=lambda r: r.get("created_at") or "")
        return rs

    def prev_version(self, version: dict) -> dict | None:
        if int(version.get("v", 0)) == 0:
            return None
        for v in self.store.find("versions", card_id=version["card_id"]):
            if int(v["v"]) == int(version["v"]) - 1:
                return v
        return None

    def evaluate(self, card: dict, version: dict, rs: list[dict], prev_rs: list[dict], max_edits: int) -> dict:
        """The numbers of one reveal, from reports only."""
        intent = card["intent"]
        ds = [self.distance(intent, r)["d_total"] for r in rs]
        F = fidelity(ds) if ds else None
        prev_ds = [self.distance(intent, r)["d_total"] for r in prev_rs]
        F_prev = fidelity(prev_ds) if prev_ds else None
        g_now = gaps(intent["axes"], [r["axes"] for r in rs]) if rs else np.zeros(8)
        g_before = gaps(intent["axes"], [r["axes"] for r in prev_rs]) if prev_rs else None
        points: dict[str, int] = {}
        ms = maker_score(ds, cfg=self.cfg()) if int(version["v"]) == 0 else None
        if ms and ms.get("points") is not None:
            points[card["maker_id"]] = points.get(card["maker_id"], 0) + int(ms["points"])
        effect = None
        edit = version.get("edit")
        if edit and int(version["v"]) >= 1:
            delta, n_pairs = paired_shift({r["reader_id"]: r["axes"] for r in prev_rs}, {r["reader_id"]: r["axes"] for r in rs})
            k = int(edit.get("bet_axis", 0))
            hit = bool(delta is not None and g_before is not None and bet_hit(float(delta[k]), float(g_before[k])))
            effect = {"bet_axis": k, "delta": _f(delta[k]) if delta is not None else None,
                      "gap_before": _f(g_before[k]) if g_before is not None else None, "hit": hit, "n_pairs": int(n_pairs),
                      "shift": _list(delta) if delta is not None else None, "points": 2 if hit else 0,
                      "editor_id": edit.get("editor_id"), "editor_nickname": edit.get("editor_nickname")}
            if hit and edit.get("editor_id"):
                points[edit["editor_id"]] = points.get(edit["editor_id"], 0) + 2
        n_human = sum(1 for r in rs if not r.get("synthetic"))
        landed_now = bool(F is not None and is_landed(F, n_human))
        landing = None
        if landed_now:
            encoders = list(dict.fromkeys(card.get("encoder_ids") or [card["maker_id"]]))
            for gid in encoders:
                points[gid] = points.get(gid, 0) + 1
            landing = {"landed": True, "threshold": LANDING_F, "points_each": 1, "encoder_ids": encoders}
        status = "landed" if landed_now else ("closed" if int(version["v"]) >= max_edits else "reading")
        return {"fidelity": _f(F) if F is not None else None, "fidelity_prev": _f(F_prev) if F_prev is not None else None,
                "delta_fidelity": _f(F - F_prev) if (F is not None and F_prev is not None) else None,
                "gaps_signed": _list(g_now), "gaps_before": _list(g_before) if g_before is not None else None,
                "maker_score": ms, "edit_effect": effect, "landing": landing, "landed": landed_now, "status": status, "points": points}

    def on_reveal(self, room: dict, rnd: dict) -> dict:
        """Called once when a read phase ends. Freezes the numbers and updates the card record (not in replay)."""
        card = self.store.get("cards", rnd["card_id"])
        version = self.store.get("versions", rnd["version_id"])
        if card is None or version is None:
            return {"status": "closed", "points": {}}
        rs = self.round_readings(rnd)
        prev = self.prev_version(version)
        prev_rs = self.round_readings(rnd, prev["id"]) if prev else []
        res = self.evaluate(card, version, rs, prev_rs, room.get("max_edits", 3))
        if rnd.get("replay"):
            res["points"] = {}
            return res
        card["status"] = res["status"]
        if res["status"] in ("landed", "closed"):
            card["finished_at"] = R.iso(R.utcnow())
            if res["status"] == "landed" and not card.get("title"):
                named = name_cluster([card["intent"]["statement"]], np.asarray(card["intent"]["axes"]),
                                     [self.elem_by_id.get(x["element_id"], {}).get("label", "") for x in version["elements"][:2]])
                card["title"], card["title_by"] = named["label"], named["by"]
        self.store.put("cards", card)
        self._grammar_cache.clear()
        if res.get("landing"):
            res["landing"]["encoders"] = [R.nickname_of(room, g) or card.get("maker_nickname") or g for g in res["landing"]["encoder_ids"]]
        return res

    def on_close(self, room: dict, rnd: dict, note: str) -> None:
        card = self.store.get("cards", rnd.get("card_id") or "")
        if card is not None and card.get("status") not in ("landed", "closed"):
            card["status"] = "closed"
            card["closed_note"] = note
            card["finished_at"] = R.iso(R.utcnow())
            self.store.put("cards", card)

    # ------------------------------------------------------------------ guest view + reveal
    def guest_view(self, room: dict, guest_id: str | None) -> dict:
        out = R.view(room, guest_id)
        rnd = room.get("round")
        if not rnd:
            return out
        deck = self.store.get("decks", room["deck_id"]) or self.playground
        role = out["you"]["role"]
        version = self.store.get("versions", rnd["version_id"]) if rnd.get("version_id") else None
        card = self.store.get("cards", rnd["card_id"]) if rnd.get("card_id") else None
        if version is not None:
            out["round"]["version"] = {"id": version["id"], "v": int(version["v"]), "elements": self.version_elements_view(version),
                                       "edit": self._edit_view(version.get("edit"))}
        prev_axes = None
        if version is not None and int(version["v"]) >= 1 and guest_id:
            prev = self.prev_version(version)
            if prev:
                for r in self.round_readings(rnd, prev["id"]):
                    if r.get("reader_id") == guest_id:
                        prev_axes = r["axes"]
        out["you"]["previous_axes"] = prev_axes
        if card is not None and role in ("maker", "editor") and guest_id == rnd.get("holder_id") and not rnd.get("replay"):
            intent = {"statement": card["intent"]["statement"], "axes": card["intent"]["axes"], "gaps_signed": None, "fidelity": None}
            if room["phase"] == "edit" and version is not None:
                rs = self.round_readings(rnd)
                if rs:
                    intent["gaps_signed"] = _list(gaps(card["intent"]["axes"], [r["axes"] for r in rs]))
                    intent["fidelity"] = _f(fidelity([self.distance(card["intent"], r)["d_total"] for r in rs]))
            out["intent"] = intent
        if room["phase"] == "reveal" and card is not None and version is not None:
            try:
                out["reveal"] = self.build_reveal(room, rnd, card, version, deck, guest_id)
            except Exception as e:
                out["reveal_error"] = f"{type(e).__name__}: {e}"
        return out

    def _edit_view(self, edit: dict | None) -> dict | None:
        if not edit:
            return None
        e = dict(edit)
        e["element_label"] = self.elem_by_id.get(edit.get("element_id"), {}).get("label", edit.get("element_id"))
        if edit.get("to_element_id"):
            e["to_element_label"] = self.elem_by_id.get(edit["to_element_id"], {}).get("label", edit["to_element_id"])
        e["bet_axis_label"] = f"{AXES[int(edit.get('bet_axis', 0))][0]} ↔ {AXES[int(edit.get('bet_axis', 0))][1]}"
        e["edited_element_id"] = edited_element_of(edit)
        return e

    def build_reveal(self, room: dict, rnd: dict, card: dict, version: dict, deck: dict, guest_id: str | None) -> dict:
        rs = self.round_readings(rnd)
        prev = self.prev_version(version)
        prev_rs = self.round_readings(rnd, prev["id"]) if prev else []
        res = rnd.get("result") or self.evaluate(card, version, rs, prev_rs, room.get("max_edits", 3))
        intent = card["intent"]
        pts = np.array([intent["axes"]] + [r["axes"] for r in rs] + [r["axes"] for r in prev_rs], dtype=float)
        xy = self.pca.transform(pts) if self.pca is not None else np.zeros((len(pts), 2))
        prev_by_reader = {r["reader_id"]: (r, xy[1 + len(rs) + i]) for i, r in enumerate(prev_rs)}
        readings, you = [], {"d_total": None, "shift": None}
        for k, r in enumerate(rs):
            d = self.distance(intent, r)
            p = prev_by_reader.get(r["reader_id"])
            shift = _list(np.asarray(r["axes"]) - np.asarray(p[0]["axes"])) if p else None
            item = {"reader_id": r.get("reader_id"), "nickname": r.get("nickname"), "axes": r["axes"], "free_text": r.get("free_text"), **d,
                    "xy": _list(xy[k + 1]), "prev_xy": _list(p[1]) if p else None, "prev_axes": p[0]["axes"] if p else None,
                    "shift": shift, "synthetic": bool(r.get("synthetic"))}
            readings.append(item)
            if r.get("reader_id") == guest_id:
                you = {"d_total": d["d_total"], "shift": shift}
        role = R.role_of(room, guest_id)
        encoder = guest_id in (card.get("encoder_ids") or []) or role in ("maker", "editor")
        public = card.get("status") in ("landed", "closed")
        g_abs = sorted(({"axis": i, "abs": abs(v), "poles": list(AXES[i])} for i, v in enumerate(res.get("gaps_signed") or [0.0] * 8)),
                       key=lambda x: -x["abs"])
        strip_after = self.grammar_strip(deck, version)
        strip_before = self.grammar_strip(deck, version, exclude_round_id=None if rnd.get("replay") else rnd["round_id"])
        landing = res.get("landing")
        if landing and "encoders" not in landing:
            landing = {**landing, "encoders": [R.nickname_of(room, g) or card.get("maker_nickname") or g for g in landing.get("encoder_ids", [])]}
        return {
            "card": {"id": card["id"], "status": res.get("status") or card.get("status"), "title": card.get("title"), "title_by": card.get("title_by"),
                     "maker_nickname": card.get("maker_nickname") or rnd.get("maker_nickname"), "v": int(version["v"]), "max_edits": room.get("max_edits", 3),
                     "landed": bool(res.get("landed")), "statement": intent["statement"] if (public or encoder) else None},
            "version": {"id": version["id"], "v": int(version["v"]), "elements": self.version_elements_view(version), "edit": self._edit_view(version.get("edit"))},
            "intent_xy": _list(xy[0]), "radius": self.config["radius"], "pca_note": "PCA frozen on the seed intents + readings; identical plane every round",
            "readings": readings, "fidelity": res.get("fidelity"), "fidelity_prev": res.get("fidelity_prev"), "delta_fidelity": res.get("delta_fidelity"),
            "gaps_abs": g_abs, "gaps_signed": res.get("gaps_signed") if encoder else None,
            "maker_score": res.get("maker_score"), "edit_effect": res.get("edit_effect"), "landing": landing,
            "verdict": self.verdict(deck, version), "grammar_strip": strip_after, "grammar_strip_before": strip_before,
            "edited_element_id": edited_element_of(version.get("edit")), "replay": bool(rnd.get("replay")), "you": you,
        }

    # ------------------------------------------------------------------ chains (§9)
    def chain(self, card: dict, room: dict | None = None) -> dict:
        deck = self.store.get("decks", card["deck_id"]) or self.playground
        versions = self.versions_of_card(card["id"])
        public = card.get("status") in ("landed", "closed")
        out_versions, prev_rs, F_prev = [], [], None
        max_edits = room["max_edits"] if room else deck.get("max_edits", 3)
        landing = None
        for v in versions:
            rs = self.readings(version_id=v["id"])
            res = self.evaluate(card, v, rs, prev_rs, max_edits)
            pts = None
            if int(v["v"]) == 0 and res["maker_score"] and res["maker_score"].get("points") is not None:
                pts = {"maker": res["maker_score"]["points"]}
            elif res["edit_effect"]:
                pts = {"editor": res["edit_effect"]["points"]}
            out_versions.append({"v": int(v["v"]), "version_id": v["id"], "elements": self.version_elements_view(v), "edit": self._edit_view(v.get("edit")),
                                 "n_readings": len(rs), "n_real": sum(1 for r in rs if not r.get("synthetic")), "fidelity": res["fidelity"],
                                 "delta_fidelity": res["delta_fidelity"], "edit_effect": res["edit_effect"], "points": pts,
                                 "edited_element_id": edited_element_of(v.get("edit")), "created_at": v.get("created_at")})
            if res.get("landing"):
                landing = {**res["landing"], "v": int(v["v"]), "encoders": [(R.nickname_of(room, g) if room else None) or card.get("maker_nickname") or g
                                                                            for g in res["landing"]["encoder_ids"]]}
            prev_rs = rs
        return {"card": {"id": card["id"], "deck_id": card["deck_id"], "mode": card.get("mode"), "status": card.get("status"), "title": card.get("title"),
                         "title_by": card.get("title_by"), "maker_nickname": card.get("maker_nickname"), "maker_id": card.get("maker_id"),
                         "landed": card.get("status") == "landed", "statement": card["intent"]["statement"] if public else None,
                         "created_at": card.get("created_at"), "finished_at": card.get("finished_at"), "max_edits": max_edits,
                         "synthetic": bool(card.get("synthetic")), "approved_editors": card.get("approved_editors", "*"),
                         "latest_version_id": card.get("latest_version_id"), "n_versions": len(versions), "closed_note": card.get("closed_note")},
                "versions": out_versions, "landing": landing}

    def deck_home(self, deck: dict, include_synthetic: bool = False, limit: int = 60) -> dict:
        cards = [c for c in self.store.find("cards", deck_id=deck["id"]) if include_synthetic or not c.get("synthetic")]
        cards.sort(key=lambda c: c.get("created_at") or "", reverse=True)
        chains = [self.chain(c) for c in cards[:limit]]
        grouped: dict[str, list] = {"reading": [], "open": [], "landed": [], "closed": []}
        for ch in chains:
            grouped.setdefault(ch["card"]["status"] or "reading", []).append(ch)
        libs = {l["id"]: l for l in self.store.all("libraries")}
        return {"deck": {**self.deck_summary(deck), "members": deck.get("members", []), "library_details": [libs.get(l, {"id": l}) for l in deck["libraries"]]},
                "cards": grouped, "n_synthetic_cards": self.store.count("cards", deck_id=deck["id"], synthetic=True)}

    def room_chains(self, room: dict) -> list[dict]:
        out = []
        for h in room.get("history", []):
            if h.get("card_id") and not h.get("replay"):
                c = self.store.get("cards", h["card_id"])
                if c:
                    out.append(self.chain(c, room))
        rnd = room.get("round")
        if rnd and rnd.get("card_id") and not rnd.get("replay"):
            c = self.store.get("cards", rnd["card_id"])
            if c and all(x["card"]["id"] != c["id"] for x in out):
                out.append(self.chain(c, room))
        return out

    # ------------------------------------------------------------------ replay script
    def replay_script(self, room: dict) -> dict:
        def script_for(card: dict, maker_nick: str | None) -> dict | None:
            versions = self.versions_of_card(card["id"])
            steps = []
            for v in versions:
                rs = self.readings(version_id=v["id"])
                if not rs:
                    continue
                steps.append({"version_id": v["id"], "v": int(v["v"]), "editor_id": (v.get("edit") or {}).get("editor_id"), "readings": rs})
            if not steps:
                return None
            return {"card_id": card["id"], "maker_id": card.get("maker_id"), "maker_nickname": maker_nick or card.get("maker_nickname"),
                    "versions": steps, "origin": card["id"]}
        for h in reversed(room.get("history", [])):
            if h.get("card_id") and not h.get("replay"):
                c = self.store.get("cards", h["card_id"])
                if c:
                    s = script_for(c, R.nickname_of(room, c.get("maker_id")))
                    if s:
                        return s
        real = [c for c in self.store.all("cards") if not c.get("synthetic") and c.get("status") in ("landed", "closed")]
        real.sort(key=lambda c: c.get("finished_at") or "", reverse=True)
        for c in real:
            s = script_for(c, None)
            if s:
                return s
        # nothing real yet: a seeded card that has an edit, shown as synthetic
        edited = [v for v in self.store.find("versions", synthetic=True) if v.get("edit")]
        edited.sort(key=lambda v: v["card_id"])
        for v in edited:
            c = self.store.get("cards", v["card_id"])
            if c:
                s = script_for(c, "seed maker")
                if s and len(s["versions"]) >= 2:
                    for step in s["versions"]:
                        step["readings"] = step["readings"][:6]
                        for k, r in enumerate(step["readings"]):
                            r["nickname"] = r.get("nickname") or f"seed {k + 1}"
                    return s
        raise R.RoomError("nothing to replay yet")

    def geometry(self) -> dict:
        cards = self.store.find("cards", synthetic=True)
        rs = self.store.find("readings", synthetic=True)
        pts = np.array([c["intent"]["axes"] for c in cards] + [r["axes"] for r in rs], dtype=float)
        xy = self.pca.transform(pts) if self.pca is not None and len(pts) else np.zeros((0, 2))
        return {"pca": self.pca.to_dict() if self.pca else None, "seed_points": [[_f(x), _f(y), k < len(cards)] for k, (x, y) in enumerate(xy)]}

"""Forks, lineage, sync from parent, upstream proposals (spec §5.10, §3.10). Pure over store docs."""
from __future__ import annotations

import re

from pixie import relay as R
from service import measure

PRIOR_MIN_READINGS = 20


class ForkError(Exception):
    def __init__(self, detail: str, status: int = 400):
        super().__init__(detail)
        self.detail, self.status = detail, status


def unique_slug(store, base: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (base or "deck").lower()).strip("-")[:40] or "deck"
    slug, k = base, 2
    while store.find("decks", slug=slug):
        slug, k = f"{base}-{k}", k + 1
    return slug


def fork(store, source: dict, user_id: str, name: str | None = None, visibility: str = "private") -> tuple[dict, dict]:
    """Copy structure, style guide, active symbols (with priors from the parent's grammar when n_readings ≥ 20,
    else the parent's prior) and every card's head version as v0. Readings and grammar are NOT copied."""
    if not (source.get("settings") or {}).get("allow_forks", True):
        raise ForkError("this deck does not allow forks", 403)
    now = R.iso(R.utcnow())
    new_id = R.new_id("d_")
    name = (name or f"{source['name']} (fork)").strip()[:80]
    parent_grammar = measure.grammar(store, source["id"])
    deck = {**{k: v for k, v in source.items() if k not in ("id", "slug", "name", "owner_id", "visibility", "origin", "stats", "lineage", "created_at", "updated_at", "synthetic")},
            "id": new_id, "slug": unique_slug(store, name), "name": name, "owner_id": user_id, "visibility": visibility,
            "origin": {"kind": "fork", "forked_from_deck_id": source["id"], "base_deck_id": (source.get("origin") or {}).get("base_deck_id")},
            "stats": {}, "lineage": {"ancestors": [source["id"]] + list((source.get("lineage") or {}).get("ancestors", [])), "children": []},
            "created_at": now, "updated_at": now}
    store.put("decks", deck)
    store.put("memberships", {"id": R.new_id("m_"), "deck_id": new_id, "user_id": user_id, "role": "owner", "joined_at": now})
    # symbols
    sym_map: dict[str, str] = {}
    n_syms = 0
    for s in store.find("symbols", deck_id=source["id"]):
        if s.get("status", "active") != "active":
            continue
        row = parent_grammar["by_id"].get(s["id"])
        if row and row["n_readings"] >= PRIOR_MIN_READINGS and any(abs(x) > 1e-9 for x in row["coef"]):
            prior, prior_source = row["coef"], "parent_grammar"
        else:
            prior, prior_source = s.get("prior_axes"), s.get("prior_source")
        sid = R.new_id("sy_")
        sym_map[s["id"]] = sid
        store.put("symbols", {**s, "id": sid, "deck_id": new_id, "origin": "inherited_fork", "inherited_from": {"deck_id": source["id"], "symbol_id": s["id"]},
                              "prior_axes": prior, "prior_source": prior_source, "status": "active", "proposed_by": None, "approved_by": None,
                              "measured": {"coef": [0.0] * 8, "ci_low": [0.0] * 8, "ci_high": [0.0] * 8, "n_cards": 0, "n_readings": 0, "n_edits": 0, "coherence": "untested", "declared_vs_measured": None},
                              "created_at": now, "updated_at": now})
        n_syms += 1
    # cards: head version → v0
    n_cards = 0
    for c in store.find("cards", deck_id=source["id"]):
        if c.get("status") == "archived" or not c.get("current_version_id"):
            continue
        head = store.get("versions", c["current_version_id"])
        if head is None:
            continue
        cid, vid = R.new_id("c_"), R.new_id("v_")
        remap = lambda items: [{**x, "symbol_id": sym_map.get(x["symbol_id"], x["symbol_id"])} for x in (items or []) if x.get("symbol_id") in sym_map]
        store.put("versions", {**head, "id": vid, "card_id": cid, "deck_id": new_id, "v": 0, "branch_key": "main", "base_version_id": head["id"],
                               "symbols_declared": remap(head.get("symbols_declared")), "symbols_detected": remap(head.get("symbols_detected")),
                               "how": {"mode": "upload", "reference_image_url": head.get("image_url"), "prompt_user": None, "prompt_full": f"forked from {source['id']}:{head['id']}",
                                       "provider": "fork", "model": "fork", "seed": None, "candidates": [], "chosen_index": 0},
                               "created_by": user_id, "created_at": now})
        store.put("cards", {**c, "id": cid, "deck_id": new_id, "maker_id": c.get("maker_id"), "status": "reading" if (c.get("intent") or {}).get("statement") else "draft",
                            "current_version_id": vid, "branches": [{"branch_key": "main", "head_version_id": vid}], "edit_requests": [], "share_token": None,
                            "forked_from_card_id": c["id"], "created_at": now, "updated_at": now})
        n_cards += 1
    snap = {"id": R.new_id("f_"), "source_deck_id": source["id"], "target_deck_id": new_id, "taken_at": now,
            "copied": {"symbols": n_syms, "cards": n_cards, "style": True, "structure": True}, "symbol_map": sym_map}
    store.put("fork_snapshots", snap)
    src_lineage = source.get("lineage") or {"ancestors": [], "children": []}
    source["lineage"] = {**src_lineage, "children": list(src_lineage.get("children", [])) + [new_id]}
    store.put("decks", source)
    return deck, snap


def lineage(store, deck: dict) -> dict:
    def summary(d: dict | None) -> dict | None:
        return None if d is None else {"id": d["id"], "slug": d.get("slug"), "name": d.get("name"), "visibility": d.get("visibility"), "origin": d.get("origin")}
    lin = deck.get("lineage") or {}
    return {"deck": summary(deck), "ancestors": [summary(store.get("decks", a)) for a in lin.get("ancestors", [])],
            "children": [summary(store.get("decks", c)) for c in lin.get("children", [])],
            "snapshots": store.find("fork_snapshots", target_deck_id=deck["id"]) + store.find("fork_snapshots", source_deck_id=deck["id"])}


def sync_from_parent(store, deck: dict, user_id: str) -> dict:
    """Cherry-pick parent symbols added since the snapshot (new keys only) and parent card versions newer than
    the snapshot for cards this fork has not touched (v0 only)."""
    parent_id = (deck.get("origin") or {}).get("forked_from_deck_id")
    snaps = store.find("fork_snapshots", target_deck_id=deck["id"])
    if not parent_id or not snaps:
        raise ForkError("not a fork")
    snap = max(snaps, key=lambda s: s["taken_at"])
    now = R.iso(R.utcnow())
    have_keys = {s.get("key") for s in store.find("symbols", deck_id=deck["id"])}
    added_symbols = 0
    for s in store.find("symbols", deck_id=parent_id):
        if s.get("status", "active") == "active" and s.get("key") not in have_keys and s.get("created_at", "") > snap["taken_at"]:
            store.put("symbols", {**s, "id": R.new_id("sy_"), "deck_id": deck["id"], "origin": "inherited_fork", "inherited_from": {"deck_id": parent_id, "symbol_id": s["id"]},
                                  "created_at": now, "updated_at": now})
            added_symbols += 1
    updated_cards = 0
    mine = {c.get("forked_from_card_id"): c for c in store.find("cards", deck_id=deck["id"]) if c.get("forked_from_card_id")}
    for pc in store.find("cards", deck_id=parent_id):
        c = mine.get(pc["id"])
        if not c or c.get("current_version_id") is None:
            continue
        my_head = store.get("versions", c["current_version_id"])
        if my_head is None or int(my_head.get("v", 0)) != 0:
            continue  # the fork edited this card; leave it
        ph = store.get("versions", pc.get("current_version_id") or "")
        if ph and ph.get("created_at", "") > snap["taken_at"] and ph["id"] != my_head.get("base_version_id"):
            vid = R.new_id("v_")
            store.put("versions", {**ph, "id": vid, "card_id": c["id"], "deck_id": deck["id"], "v": 0, "branch_key": "main", "base_version_id": ph["id"], "created_by": user_id, "created_at": now})
            c["current_version_id"] = vid
            c["branches"] = [{"branch_key": "main", "head_version_id": vid}]
            store.put("cards", c)
            updated_cards += 1
    snap["taken_at"] = now
    store.put("fork_snapshots", snap)
    measure.invalidate(deck["id"])
    return {"added_symbols": added_symbols, "updated_cards": updated_cards}


def propose_upstream(store, from_deck: dict, user_id: str, kind: str, ref_id: str, note: str) -> dict:
    to_id = (from_deck.get("origin") or {}).get("forked_from_deck_id")
    if not to_id:
        raise ForkError("only forks can propose upstream")
    if kind not in ("version", "symbol"):
        raise ForkError("kind must be version or symbol", 422)
    doc = {"id": R.new_id("up_"), "from_deck_id": from_deck["id"], "to_deck_id": to_id, "kind": kind, "version_id": ref_id if kind == "version" else None,
           "symbol_id": ref_id if kind == "symbol" else None, "note": (note or "")[:280], "status": "open", "proposed_by": user_id, "decided_by": None,
           "decision_note": None, "result_ref": None, "created_at": R.iso(R.utcnow()), "updated_at": R.iso(R.utcnow())}
    store.put("upstream_proposals", doc)
    return doc


def decide_upstream(store, proposal: dict, user_id: str, accept: bool, note: str | None = None) -> dict:
    if proposal.get("status") != "open":
        raise ForkError("already decided", 409)
    now = R.iso(R.utcnow())
    proposal.update({"status": "accepted" if accept else "declined", "decided_by": user_id, "decision_note": (note or "")[:280] or None, "updated_at": now})
    if accept:
        to_id = proposal["to_deck_id"]
        if proposal["kind"] == "symbol":
            s = store.get("symbols", proposal["symbol_id"])
            if s is None:
                raise ForkError("symbol no longer exists", 404)
            sid = R.new_id("sy_")
            store.put("symbols", {**s, "id": sid, "deck_id": to_id, "origin": "upstream", "inherited_from": {"deck_id": proposal["from_deck_id"], "symbol_id": s["id"]},
                                  "status": "active", "approved_by": user_id, "approved_at": now, "created_at": now, "updated_at": now})
            proposal["result_ref"] = sid
        else:
            v = store.get("versions", proposal["version_id"])
            if v is None:
                raise ForkError("version no longer exists", 404)
            fc = store.get("cards", v["card_id"])
            target = None
            if fc and fc.get("forked_from_card_id"):
                target = store.get("cards", fc["forked_from_card_id"])
            if target is None or target.get("deck_id") != to_id:
                raise ForkError("no matching card in the parent deck", 409)
            snaps = store.find("fork_snapshots", target_deck_id=proposal["from_deck_id"])
            sym_map = {v2: k for s2 in snaps for k, v2 in (s2.get("symbol_map") or {}).items()}  # fork symbol id → parent symbol id
            branch_key = f"upstream-{proposal['id'][-6:]}"
            vid = R.new_id("v_")
            remap = lambda items: [{**x, "symbol_id": sym_map.get(x["symbol_id"], x["symbol_id"])} for x in (items or [])]
            store.put("versions", {**v, "id": vid, "card_id": target["id"], "deck_id": to_id, "v": int(v.get("v", 0)), "branch_key": branch_key,
                                   "base_version_id": target.get("current_version_id"), "symbols_declared": remap(v.get("symbols_declared")),
                                   "symbols_detected": remap(v.get("symbols_detected")), "created_by": user_id, "created_at": now})
            target.setdefault("branches", []).append({"branch_key": branch_key, "head_version_id": vid})
            store.put("cards", target)
            proposal["result_ref"] = vid
        measure.invalidate(to_id)
    store.put("upstream_proposals", proposal)
    return proposal

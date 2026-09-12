"""v5 services over the synthetic playground deck: measurement (slice 7), sessions (8), coherence (9), forks (10),
readings (7). Memory store, hash embedder, no HTTP."""
import os
import sys
from datetime import timedelta

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.dirname(HERE)
sys.path.insert(0, API)
os.environ.setdefault("PIXIE_EMBED", "hash")
os.environ.setdefault("PIXIE_N_BOOT", "30")
DATA = os.path.join(API, "..", "data")

from pixie import relay as R  # noqa: E402
from pixie.store import MemoryStore  # noqa: E402
from service import coherence, forks, measure, readings as RD, seeds, sessions as S  # noqa: E402


@pytest.fixture(scope="module")
def store():
    s = MemoryStore()
    seeds.ensure_playground(s, DATA)
    return s


@pytest.fixture(scope="module")
def deck(store):
    return store.get("decks", seeds.DECK_ID)


def test_seed_estimator(store, deck):
    g = measure.grammar(store, deck["id"])
    p = seeds.planted(store)
    W = np.array([r["coef"] for r in g["symbols"]])
    Ws = np.array([p["W_star"].get(r["symbol_id"], [0] * 8) for r in g["symbols"]])
    assert np.corrcoef(W.ravel(), Ws.ravel())[0, 1] > 0.8
    assert g["n_readings"] == 620 and g["n_edits"] == 40
    assert sum(1 for r in g["symbols"] if r["n_edits"] > 0) >= 20
    for cid, want in ((p["polysemous_card_id"], "polysemous"), (p["noisy_card_id"], "noisy")):
        v0 = [v for v in store.find("versions", card_id=cid) if v["v"] == 0][0]
        assert measure.verdict(store, deck["id"], v0)["verdict"] == want


def test_coherence_dashboard(store, deck):
    d = coherence.dashboard(store, deck)
    se = d["semantic"]
    assert se["n_consistent"] + se["n_contested"] + se["n_untested"] == 43
    assert d["coherence_index"] is None or 0 <= d["coherence_index"] <= 1
    assert d["transmission"]["mean_fidelity"] is not None
    assert set(d["work"]) == {"contested", "off_style", "needs_readings", "empty"}


def _new_card(store, deck, maker="u_maker", sym_ids=None):
    now = R.iso(R.utcnow())
    syms = [s for s in measure.active_symbols(store, deck["id"])][:3] if sym_ids is None else [store.get("symbols", i) for i in sym_ids]
    cid, vid = R.new_id("c_"), R.new_id("v_")
    store.put("cards", {"id": cid, "deck_id": deck["id"], "position_key": "free-test", "maker_id": maker, "intent": {"statement": "a quiet ending", "axes": [1, 3, -1, -2, 0, -3, 1, -2], "embedding": None},
                        "approved_editors": "*", "edit_requests": [], "status": "reading", "current_version_id": vid, "branches": [{"branch_key": "main", "head_version_id": vid}],
                        "encoder_ids": [maker], "created_at": now, "updated_at": now})
    store.put("versions", {"id": vid, "card_id": cid, "deck_id": deck["id"], "v": 0, "branch_key": "main", "base_version_id": None, "image_url": None,
                           "symbols_declared": [{"symbol_id": s["id"]} for s in syms], "symbols_detected": [{"symbol_id": s["id"], "salience": 0.8, "tagged_by": "human"} for s in syms],
                           "how": {"mode": "prompt", "provider": "local"}, "checks": {"style_score": 0.9}, "created_by": maker, "created_at": now})
    return store.get("cards", cid), store.get("versions", vid)


def test_readings_queue_and_status_machine(store, deck):
    card, v0 = _new_card(store, deck)
    q = RD.next_to_read(store, deck, "u_r1")
    assert q and q["card_id"] == card["id"] and q["version"]["id"] == v0["id"]
    with pytest.raises(RD.ReadingError):
        RD.submit(store, deck, v0, "u_maker", {"axes": [0] * 8})
    for uid in ("u_r1", "u_r2"):
        RD.submit(store, deck, v0, uid, {"axes": [2, 2, 2, 2, 2, 2, 2, 2]})
    assert store.get("cards", card["id"])["status"] == "reading"
    _, c = RD.submit(store, deck, v0, "u_r3", {"axes": [2, 2, 2, 2, 2, 2, 2, 2], "free_text": "far away"})
    assert c["status"] == "open"  # threshold reached, far from the intent
    assert RD.next_to_read(store, deck, "u_r1") is None or RD.next_to_read(store, deck, "u_r1")["card_id"] != card["id"]
    with pytest.raises(RD.ReadingError):
        RD.submit(store, deck, v0, "u_r1", {"axes": [0] * 8})  # twice
    rev = measure.reveal(store, deck, c, v0, "u_r1", encoder=False)
    assert rev["card"]["statement"] is None and rev["gaps_signed"] is None and rev["intent_xy"] is not None  # star after threshold
    assert rev["you"]["d_total"] is not None and rev["readings"][0]["reader_id"] is None  # anonymised for readers
    rev_m = measure.reveal(store, deck, c, v0, "u_maker", encoder=True)
    assert rev_m["card"]["statement"] == "a quiet ending" and len(rev_m["gaps_signed"]) == 8 and rev_m["maker_score"]["points"] == 0
    # landing: a new card whose readers land on the intent
    card2, v = _new_card(store, deck, maker="u_maker2")
    for uid in ("u_a", "u_b", "u_c"):
        _, c2 = RD.submit(store, deck, v, uid, {"axes": [1, 3, -1, -2, 0, -3, 1, -2]})
    assert c2["status"] == "landed"


def test_relay_session_flow(store, deck):
    card, v0 = _new_card(store, deck, maker="u_host")
    s = S.create(store, deck, "u_host", "host", mode="relay", settings={"read_timer": 60, "edit_timer": 45})
    for uid, n in (("u_p1", "p1"), ("u_p2", "p2"), ("g_x", "guest")):
        s = S.join(store, s, uid, n, is_guest=uid.startswith("g_"))
    assert len(s["players"]) == 4 and s["turn_order"] == ["u_host", "u_p1", "u_p2", "g_x"]  # guests take turns too
    with pytest.raises(S.SessionError):
        S.start(store, s, "u_p1")
    s = S.start(store, s, "u_host")
    assert s["state"] == "compose" and s["current_maker_id"] == "u_host"
    s = S.choose_card(store, deck, s, "u_host", card)
    assert s["state"] == "read"
    rd = store.get("rounds", s["current_round_id"])
    assert set(rd["reader_ids"]) == {"u_p1", "u_p2", "g_x"}
    view = S.view(store, deck, s, "u_p1")
    assert view["you"]["role"] == "reader" and "intent" not in view
    assert "intent" in S.view(store, deck, s, "u_host")
    for uid, ax in (("u_p1", [1, 3, -1, -2, 0, -3, 1, -2]), ("u_p2", [1, 2, -1, -2, 1, -2, 1, -1]), ("g_x", [-3, -3, 3, 3, 3, 3, -3, 3])):
        s = S.submit_reading(store, deck, s, uid, {"axes": ax})
    assert s["state"] == "reveal" and s["scores"].get("u_host") == 3
    v = S.view(store, deck, s, "g_x")
    assert v["reveal"]["you"]["d_total"] is not None and v["reveal"]["card"]["statement"] is None
    s = S.advance(store, deck, s, "u_host")
    assert s["state"] == "edit" and s["current_editor_id"] == "u_p1"
    # the editor's op → generating → the job attaches a new version → paired re-read
    s = S.begin_edit(store, s, "u_p1", job_id="j_test")
    assert s["state"] == "generating"
    now = R.iso(R.utcnow())
    v1 = {**v0, "id": R.new_id("v_"), "v": 1, "base_version_id": v0["id"], "symbols_detected": v0["symbols_detected"] + [{"symbol_id": measure.active_symbols(store, deck["id"])[5]["id"], "salience": 0.7, "tagged_by": "human"}],
          "how": {"op": "add", "symbol_id": measure.active_symbols(store, deck["id"])[5]["id"], "bet_axis": 4, "rationale": "needs gain", "editor_id": "u_p1", "counts_as_experiment": True}, "created_at": now}
    store.put("versions", v1)
    c = store.get("cards", card["id"]); c["current_version_id"] = v1["id"]; c.setdefault("encoder_ids", []).append("u_p1"); store.put("cards", c)
    s = S.attach_edit(store, deck, s, v1)
    assert s["state"] == "read" and s["edits_this_card"] == 1
    rd = store.get("rounds", s["current_round_id"])
    assert "u_p1" not in rd["reader_ids"] and "u_host" not in rd["reader_ids"]  # editor holds the card; the maker still never reads their own card
    assert S.view(store, deck, s, "u_p2")["you"]["previous_axes"] == [1, 2, -1, -2, 1, -2, 1, -1]
    for uid, ax in (("u_p2", [1, 3, -1, -2, 0, -3, 1, -2]), ("g_x", [1, 3, -1, -2, 0, -3, 1, -2])):
        s = S.submit_reading(store, deck, s, uid, {"axes": ax})
    assert s["state"] == "reveal"
    rd = store.get("rounds", s["current_round_id"])
    assert rd["result"]["landed"] and rd["result"]["edit_effect"]["n_pairs"] == 2
    assert s["scores"].get("u_p1", 0) >= 1  # landing (+2 if the bet hit)
    s = S.advance(store, deck, s, "u_host")
    assert s["state"] == "compose" and s["current_maker_id"] == "u_p1" and s["makers_done"] == ["u_host"]
    # timers: compose expiry skips the maker
    s["round_ends_at"] = R.iso(R.utcnow() - timedelta(seconds=1)); store.put("sessions", s)
    s = S.tick(store, deck, s)
    assert s["current_maker_id"] == "u_p2"
    summ = S.summary(store, s)
    assert len(summ["cards"]) == 2 and any(x["bet_hit"] is not None for x in summ["cards"])


def test_fork_and_upstream(store, deck):
    src = store.get("decks", deck["id"])
    d2, snap = forks.fork(store, src, "u_forker", name="My fork")
    assert d2["origin"]["kind"] == "fork" and d2["origin"]["forked_from_deck_id"] == deck["id"]
    assert snap["copied"]["symbols"] == 43 and snap["copied"]["cards"] >= 60
    syms = store.find("symbols", deck_id=d2["id"])
    assert all(s["origin"] == "inherited_fork" and s["prior_source"] == "parent_grammar" for s in syms)  # parent has 620 readings
    assert store.count("readings", deck_id=d2["id"]) == 0
    lin = forks.lineage(store, d2)
    assert lin["ancestors"][0]["id"] == deck["id"] and deck["id"] in [a["id"] for a in lin["ancestors"]]
    assert d2["id"] in store.get("decks", deck["id"])["lineage"]["children"]
    # a fork symbol proposed upstream lands as origin: upstream
    s0 = syms[0]
    pr = forks.propose_upstream(store, d2, "u_forker", "symbol", s0["id"], "please take this")
    with pytest.raises(forks.ForkError):
        forks.propose_upstream(store, src, "u_x", "symbol", s0["id"], "not a fork")
    pr = forks.decide_upstream(store, pr, "u_curator", accept=True)
    assert pr["status"] == "accepted" and store.get("symbols", pr["result_ref"])["origin"] == "upstream"
    # a fork version proposed upstream lands as a branch on the parent card
    fc = next(c for c in store.find("cards", deck_id=d2["id"]) if c.get("forked_from_card_id"))
    pr2 = forks.decide_upstream(store, forks.propose_upstream(store, d2, "u_forker", "version", fc["current_version_id"], "try this"), "u_curator", True)
    parent_card = store.get("cards", fc["forked_from_card_id"])
    assert any(b["head_version_id"] == pr2["result_ref"] for b in parent_card["branches"]) and store.get("versions", pr2["result_ref"])["branch_key"].startswith("upstream-")
    assert forks.sync_from_parent(store, d2, "u_forker")["added_symbols"] >= 0

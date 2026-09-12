"""State-machine tests for pixie.relay with the memory store. No engine, no data."""
import os
import sys
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pixie import relay as R
from pixie.store import MemoryStore

DECK = {"id": "PLAY", "code": "PLAY", "max_edits": 3}


def card(maker):
    return {"id": R.new_id("c_"), "deck_id": "PLAY", "maker_id": maker, "intent": {"statement": "s", "axes": [0] * 8}, "status": "reading", "encoder_ids": [maker]}


def version(cid, v=0, edit=None):
    return {"id": R.new_id("v_"), "card_id": cid, "deck_id": "PLAY", "v": v, "elements": [{"element_id": "star", "slot": "top"}, {"element_id": "sun", "slot": "bottom"}], "edit": edit}


def reading(gid, axes=None):
    return {"id": R.new_id("r_"), "reader_id": gid, "axes": axes or [1] * 8, "free_text": None, "synthetic": False, "created_at": R.iso(R.utcnow())}


def make_room(n=3):
    s = MemoryStore()
    host, room = R.create_room(s, DECK, "host", None)
    others = []
    for i in range(n - 1):
        g, room = R.join_room(s, room["code"], f"p{i}", None)
        others.append(g)
    return s, host, others, room


def test_full_relay_lands_then_next_maker():
    s, host, (a, b), room = make_room(3)
    with pytest.raises(R.RoomError):
        R.start(s, room, a)
    room = R.start(s, room, host)
    assert room["phase"] == "compose" and room["round"]["maker_id"] == host and room["round"]["v"] == 0
    assert R.role_of(room, host) == "maker" and R.role_of(room, a) == "reader"
    c = card(host)
    with pytest.raises(R.RoomError):
        R.compose(s, room, a, c, version(c["id"]))
    room = R.compose(s, room, host, c, version(c["id"]))
    assert room["phase"] == "read" and set(room["round"]["reader_ids"]) == {a, b}
    with pytest.raises(R.RoomError):
        R.submit_reading(s, room, host, reading(host))
    calls = []

    def on_reveal(room_, rnd):
        calls.append(rnd["v"])
        return {"status": "reading", "points": {host: 3}, "fidelity": 0.5}

    room = R.submit_reading(s, room, a, reading(a), on_reveal=on_reveal)
    assert room["phase"] == "read"
    room = R.submit_reading(s, room, b, reading(b), on_reveal=on_reveal)
    assert room["phase"] == "reveal" and calls == [0] and room["scores"][host] == 3
    # continue → edit by the next player after the holder who is not the maker
    room = R.continue_reveal(s, room, host, on_reveal=on_reveal)
    assert room["phase"] == "edit" and room["round"]["editor_id"] == a and room["round"]["holder_id"] == a
    assert R.role_of(room, a) == "editor" and R.role_of(room, host) == "reader" and R.role_of(room, b) == "reader"
    v1 = version(c["id"], 1, edit={"type": "swap", "element_id": "sun", "to_element_id": "moon", "editor_id": a, "bet_axis": 2})
    with pytest.raises(R.RoomError):
        R.submit_edit(s, room, b, v1)
    room = R.submit_edit(s, room, a, v1)
    assert room["phase"] == "read" and room["round"]["v"] == 1 and set(room["round"]["reader_ids"]) == {host, b}
    assert s.get("cards", c["id"])["latest_version_id"] == v1["id"] and a in s.get("cards", c["id"])["encoder_ids"]

    def on_reveal_land(room_, rnd):
        return {"status": "landed", "points": {a: 2, host: 1}, "fidelity": 0.9}

    room = R.submit_reading(s, room, host, reading(host), on_reveal=on_reveal_land)
    room = R.submit_reading(s, room, b, reading(b), on_reveal=on_reveal_land)
    assert room["phase"] == "reveal" and room["scores"] == {host: 4, a: 2}
    room = R.continue_reveal(s, room, host)
    assert room["phase"] == "compose" and room["round"]["maker_id"] == a and room["makers_done"] == [host]
    assert room["history"][-1]["status"] == "landed" and room["n_cards"] == 2


def test_edit_budget_closes_card_and_room_ends_after_everyone_made():
    s, host, (a,), room = make_room(2)
    room = R.start(s, room, host)
    assert room.get("small_room") is True
    c = card(host)
    room = R.compose(s, room, host, c, version(c["id"]))
    on_reveal = lambda r, rnd: {"status": "reading", "points": {}}
    for v in range(0, 4):  # v0 + three edits = the budget
        reader = a if v == 0 else host  # once `a` holds the card, the maker is the only reader
        room = R.submit_reading(s, room, reader, reading(reader), on_reveal=on_reveal)
        assert room["phase"] == "reveal", (v, room["phase"])
        room = R.continue_reveal(s, room, host, on_reveal=on_reveal)
        if v < 3:
            assert room["phase"] == "edit" and room["round"]["editor_id"] == a
            room = R.submit_edit(s, room, a, version(c["id"], v + 1, edit={"type": "add", "element_id": "moon", "editor_id": a, "bet_axis": 0}))
            assert room["phase"] == "read" and room["round"]["v"] == v + 1
    # v == max_edits (3) → closed → next maker (a)
    assert room["phase"] == "compose" and room["round"]["maker_id"] == a and room["history"][-1]["status"] == "closed"
    c2 = card(a)
    room = R.compose(s, room, a, c2, version(c2["id"]))
    room = R.submit_reading(s, room, host, reading(host), on_reveal=lambda r, rnd: {"status": "landed", "points": {a: 1}})
    room = R.continue_reveal(s, room, host)
    assert room["phase"] == "ended" and room["round"] is None and set(room["makers_done"]) == {host, a}


def test_timeouts():
    s, host, (a, b), room = make_room(3)
    room = R.start(s, room, host)
    later = R.utcnow() + timedelta(seconds=R.T_COMPOSE + 1)
    room = R.tick(s, room, now=later)
    assert room["phase"] == "compose" and room["round"]["maker_id"] == a and room["history"][-1]["status"] == "skipped"
    c = card(a)
    room = R.compose(s, room, a, c, version(c["id"]))
    later = R.utcnow() + timedelta(seconds=R.T_READ_V0 + 1)
    room = R.tick(s, room, now=later, on_reveal=lambda r, rnd: {"status": "reading", "points": {a: 0}})
    assert room["phase"] == "reveal"
    later2 = later + timedelta(seconds=R.T_REVEAL + 1)
    room = R.tick(s, room, now=later2)
    assert room["phase"] == "edit" and room["round"]["editor_id"] == b  # next after holder a, not maker
    closed = []
    later3 = later2 + timedelta(seconds=R.T_EDIT + 1)
    room = R.tick(s, room, now=later3, on_close=lambda r, rnd, note: closed.append(note))
    assert closed == ["editor timed out"] and room["phase"] == "compose" and room["round"]["maker_id"] == b


def test_replay_steps_through_versions():
    s, host, (a,), room = make_room(2)
    r0 = [reading("x"), reading("y")]
    r1 = [reading("x", [2] * 8), reading("y", [2] * 8)]
    script = {"card_id": "c_1", "maker_id": host, "maker_nickname": "host",
              "versions": [{"version_id": "v_0", "v": 0, "readings": r0}, {"version_id": "v_1", "v": 1, "editor_id": a, "readings": r1}], "origin": "c_1"}
    with pytest.raises(R.RoomError):
        R.start_replay(s, room, a, script)
    room = R.start_replay(s, room, host, script)
    assert room["phase"] == "read" and room["round"]["replay"] and room["round"]["v"] == 0
    now = R.utcnow()
    assert R.view(room, a, now)["round"]["n_submitted"] == 0
    mid = now + timedelta(seconds=R.REPLAY_READ / 2 + 0.2)
    assert R.view(room, a, mid)["round"]["n_submitted"] == 1
    t1 = now + timedelta(seconds=R.REPLAY_READ + 2)
    room = R.tick(s, room, now=t1, on_reveal=lambda r, rnd: {"status": "reading", "points": {host: 3}})
    assert room["phase"] == "reveal" and room["scores"] == {}  # replay never scores
    t2 = t1 + timedelta(seconds=R.REPLAY_REVEAL + 1)
    room = R.tick(s, room, now=t2)
    assert room["phase"] == "read" and room["round"]["v"] == 1 and room["round"]["holder_id"] == a
    t3 = t2 + timedelta(seconds=R.REPLAY_READ + 2)
    room = R.tick(s, room, now=t3, on_reveal=lambda r, rnd: {"status": "landed", "points": {}})
    assert room["phase"] == "reveal"
    t4 = t3 + timedelta(seconds=R.REPLAY_REVEAL + 1)
    room = R.tick(s, room, now=t4)
    assert room["phase"] == "reveal" and room["round"]["replay_done"] is True
    room = R.end_replay(s, room, host)
    assert room["phase"] == "lobby" and s.count("readings") == 0

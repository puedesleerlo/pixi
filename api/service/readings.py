"""Async readings (spec §5.8) and the card status machine transitions driven by readings (spec §3.12).
Pure functions over store docs; routers add auth."""
from __future__ import annotations

from pixie import relay as R
from service import measure


class ReadingError(Exception):
    def __init__(self, detail: str, status: int = 400):
        super().__init__(detail)
        self.detail, self.status = detail, status


def eligible_readers(store, deck: dict, card: dict) -> int:
    """Members of the deck other than the card's maker: the people who can actually read it."""
    members = {m["user_id"] for m in store.find("memberships", deck_id=deck["id"])}
    members.discard(card.get("maker_id"))
    return len(members)


def effective_threshold(store, deck: dict, card: dict) -> int:
    """`ready_threshold` capped by the number of eligible members, never below 1: a two-person deck opens a
    card after one reading instead of waiting forever for a third reader (owner's decision, Sat 04:40)."""
    thr = int((deck.get("settings") or {}).get("ready_threshold", 3))
    return max(1, min(thr, max(1, eligible_readers(store, deck, card))))


def next_to_read(store, deck: dict, reader_id: str | None) -> dict | None:
    """The version with the fewest human readings among cards in `reading`, skipping versions this reader
    already read and cards they made."""
    best = None
    counts = {"own": 0, "already_read": 0, "candidates": 0}
    for c in store.find("cards", deck_id=deck["id"], status="reading"):
        if c.get("synthetic") or not c.get("current_version_id"):
            continue
        if c.get("maker_id") == reader_id:
            counts["own"] += 1
            continue
        v = store.get("versions", c["current_version_id"])
        if v is None:
            continue
        rs = store.find("readings", version_id=v["id"])
        if reader_id and any(r.get("reader_id") == reader_id for r in rs):
            counts["already_read"] += 1
            continue
        counts["candidates"] += 1
        n_h = len(measure.human(rs))
        if best is None or n_h < best[0]:
            best = (n_h, c, v)
    if best is None:
        reason = "all_read" if counts["already_read"] else ("own_cards_only" if counts["own"] else "no_cards")
        return {"empty": True, "reason": reason, **counts}
    n_h, c, v = best
    prev_axes = None
    if v.get("base_version_id") and reader_id:
        for r in store.find("readings", version_id=v["base_version_id"]):
            if r.get("reader_id") == reader_id:
                prev_axes = r["axes"]
    return {"card_id": c["id"], "position_key": c.get("position_key"), "version": _public_version(v), "n_human_readings": n_h,
            "ready_threshold": effective_threshold(store, deck, c), "previous_axes": prev_axes}


def _public_version(v: dict) -> dict:
    return {"id": v["id"], "v": int(v.get("v", 0)), "image_url": v.get("image_url"), "thumb_url": v.get("thumb_url"), "width": v.get("width"), "height": v.get("height")}


def submit(store, deck: dict, version: dict, reader_id: str, body: dict, embed_fn=None, session_id: str | None = None, round_id: str | None = None,
           nickname: str | None = None) -> tuple[dict, dict]:
    """Store one reading; then advance the card per the status machine. Returns (reading, card)."""
    card = store.get("cards", version["card_id"])
    if card is None:
        raise ReadingError("no such card", 404)
    if card.get("status") not in ("reading", "open") and session_id is None:
        raise ReadingError("this card is not collecting readings", 409)
    if card.get("maker_id") == reader_id:
        raise ReadingError("the maker does not read their own card")
    if any(r.get("reader_id") == reader_id for r in store.find("readings", version_id=version["id"])):
        raise ReadingError("you already read this version")
    axes = [float(a) for a in body["axes"]]
    if len(axes) != 8 or any(a < -3 or a > 3 for a in axes):
        raise ReadingError("axes must be eight values within -3..3", 422)
    text = (body.get("free_text") or "").strip()[:140] or None
    emb = None
    if text and embed_fn is not None:
        try:
            emb = [float(x) for x in embed_fn([text])[0]]
        except Exception:
            emb = None
    reading = {"id": R.new_id("r_"), "deck_id": deck["id"], "card_id": card["id"], "version_id": version["id"], "reader_id": reader_id, "nickname": nickname,
               "session_id": session_id, "round_id": round_id, "free_text": text, "axes": axes, "embedding": emb, "latency_ms": body.get("latency_ms"),
               "synthetic": False, "created_at": R.iso(R.utcnow())}
    store.put("readings", reading)
    measure.invalidate(deck["id"])
    if session_id is None:  # live rounds decide landing/closing when the round ends (service.sessions._reveal)
        card = advance_status(store, deck, card, version)
    return reading, card


def advance_status(store, deck: dict, card: dict, version: dict) -> dict:
    """reading ──(≥ ready_threshold human readings)──► open; open/reading ──(F ≥ 0.80)──► landed;
    ──(edits = max_edits)──► closed. Only applies to the card's head version on main."""
    if card.get("status") not in ("reading", "open") or card.get("current_version_id") != version["id"]:
        return card
    settings = deck.get("settings") or {}
    thr = effective_threshold(store, deck, card)
    max_edits = int(settings.get("max_edits_per_card", 6))
    rs = measure.version_readings(store, version["id"])
    n_h = len(measure.human(rs))
    if n_h < thr:
        return card
    prev = store.get("versions", version["base_version_id"]) if version.get("base_version_id") else None
    res = measure.evaluate_version(card, version, rs, measure.version_readings(store, prev["id"]) if prev else [], max_edits)
    new_status = res["next_status"] or "open"
    if new_status != card.get("status"):
        card["status"] = new_status
        if new_status in ("landed", "closed"):
            card["finished_at"] = R.iso(R.utcnow())
        card["updated_at"] = R.iso(R.utcnow())
        store.put("cards", card)
    return card


def open_for_edits(store, deck: dict, card: dict, user_id: str, is_curator: bool) -> dict:
    """The maker or a curator opens a card for edits before the threshold is met. Needs at least one human
    reading so an edit's bet has a baseline. Never a veto: this only widens what editors may do."""
    if card.get("maker_id") != user_id and not is_curator:
        raise ReadingError("only the maker or a curator can open a card early", 403)
    if card.get("status") != "reading":
        raise ReadingError(f"this card is {card.get('status')}, not collecting readings", 409)
    v = store.get("versions", card.get("current_version_id") or "")
    n_h = len(measure.human(store.find("readings", version_id=v["id"]))) if v else 0
    if n_h < 1:
        raise ReadingError("the card needs at least one reading before it can be edited", 409)
    card["status"] = "open"
    card["opened_early_by"] = user_id
    card["updated_at"] = R.iso(R.utcnow())
    store.put("cards", card)
    return card

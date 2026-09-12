"""Decks (spec §3.3–3.4, §5.2, §5.10): wizard, structure templates, stats, members, invitations, forks."""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from auth import new_id
from models import (Card, Deck, DeckCreate, DeckOrigin, DeckPatch, DeckSettings, ForkSnapshot, Invitation, Membership, Position,
                    ReferenceImage, StructureTemplate, StyleGuide, Symbol, SymbolDeclared, SymbolDetected, Version, now_iso)
from service import activity, notifications

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRUCTURES_PATH = os.environ.get("PIXIE_STRUCTURES", os.path.join(HERE, "..", "data", "structures.json"))

MAJORS = ["The Fool", "The Magician", "The High Priestess", "The Empress", "The Emperor", "The Hierophant", "The Lovers",
          "The Chariot", "Strength", "The Hermit", "Wheel of Fortune", "Justice", "The Hanged Man", "Death", "Temperance",
          "The Devil", "The Tower", "The Star", "The Moon", "The Sun", "Judgement", "The World"]
RANKS = [("01", "Ace"), ("02", "Two"), ("03", "Three"), ("04", "Four"), ("05", "Five"), ("06", "Six"), ("07", "Seven"),
         ("08", "Eight"), ("09", "Nine"), ("10", "Ten"), ("page", "Page"), ("knight", "Knight"), ("queen", "Queen"), ("king", "King")]
SUITS = ["Wands", "Cups", "Swords", "Pentacles"]
LENORMAND = ["Rider", "Clover", "Ship", "House", "Tree", "Clouds", "Snake", "Coffin", "Bouquet", "Scythe", "Whip", "Birds", "Child",
             "Fox", "Bear", "Stars", "Stork", "Dog", "Tower", "Garden", "Mountain", "Crossroads", "Mice", "Heart", "Ring", "Book",
             "Letter", "Man", "Woman", "Lily", "Sun", "Moon", "Key", "Fish", "Anchor", "Cross"]
MANTEGNA = [("Conditions of Man", ["Misero", "Fameio", "Artixan", "Merchadante", "Zintilomo", "Cavalier", "Doxe", "Re", "Imperator", "Papa"]),
            ("Apollo and the Muses", ["Calliope", "Urania", "Terpsicore", "Erato", "Polimnia", "Talia", "Melpomene", "Euterpe", "Clio", "Apollo"]),
            ("Liberal Arts", ["Grammatica", "Loica", "Rhetorica", "Geometria", "Aritmetricha", "Musicha", "Poesia", "Philosofia", "Astrologia", "Theologia"]),
            ("Virtues and Principles", ["Iliaco", "Chronico", "Cosmico", "Temperancia", "Prudencia", "Forteza", "Justicia", "Charita", "Speranza", "Fede"]),
            ("Spheres", ["Luna", "Mercurio", "Venus", "Sol", "Marte", "Jupiter", "Saturno", "Octava Spera", "Primo Mobile", "Prima Causa"])]


def _majors() -> list[Position]:
    return [Position(key=f"major-{i:02d}", title=t, group="Majors", order=i) for i, t in enumerate(MAJORS)]


def _minors() -> list[Position]:
    out, k = [], 22
    for suit in SUITS:
        for rk, rt in RANKS:
            out.append(Position(key=f"{suit.lower()}-{rk}", title=f"{rt} of {suit}", group=suit, order=k))
            k += 1
    return out


def builtin_structures() -> dict[str, StructureTemplate]:
    return {
        "tarot78": StructureTemplate(id="tarot78", key="tarot78", name="Tarot · 78 cards", positions=_majors() + _minors()),
        "majors22": StructureTemplate(id="majors22", key="majors22", name="Major Arcana · 22", positions=_majors()),
        "minors56": StructureTemplate(id="minors56", key="minors56", name="Minor Arcana · 56", positions=_minors()),
        "lenormand36": StructureTemplate(id="lenormand36", key="lenormand36", name="Petit Lenormand · 36",
                                         positions=[Position(key=f"len-{i + 1:02d}", title=t, group="Lenormand", order=i) for i, t in enumerate(LENORMAND)]),
        "mantegna50": StructureTemplate(id="mantegna50", key="mantegna50", name="Tarocchi del Mantegna · 50",
                                        positions=[Position(key=f"mant-{gi * 10 + i + 1:02d}", title=t, group=g, order=gi * 10 + i)
                                                   for gi, (g, titles) in enumerate(MANTEGNA) for i, t in enumerate(titles)]),
        "free": StructureTemplate(id="free", key="free", name="Free · no fixed positions", positions=[]),
    }


_structures_cache: dict[str, StructureTemplate] | None = None


def structures() -> dict[str, StructureTemplate]:
    global _structures_cache
    if _structures_cache is not None:
        return _structures_cache
    out = builtin_structures()
    try:
        if os.path.exists(STRUCTURES_PATH):
            with open(STRUCTURES_PATH) as f:
                raw = json.load(f)
            items = raw if isinstance(raw, list) else raw.get("templates", [])
            for t in items:
                st = StructureTemplate(**{**t, "id": t.get("id") or t.get("key")})
                out[st.key] = st
    except Exception as e:  # keep the fallback
        print(f"[decks] structures.json unreadable ({e}); using built-in templates")
    _structures_cache = out
    return out


def structure(key: str) -> StructureTemplate:
    st = structures().get(key)
    if st is None:
        raise HTTPException(422, {"code": "validation", "detail": f"unknown structure template {key!r}"})
    return st


# ----------------------------------------------------------------------------- helpers
def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:48] or "deck"


def unique_slug(store, name: str) -> str:
    base = slugify(name)
    slug, k = base, 2
    while store.find("decks", slug=slug):
        slug = f"{base}-{k}"
        k += 1
    return slug


def get_deck(store, id_or_slug: str) -> Deck:
    d = store.get("decks", id_or_slug)
    if d is None:
        rows = store.find("decks", slug=id_or_slug)
        d = rows[0] if rows else None
    if d is None:
        raise HTTPException(404, {"code": "not_found", "detail": "no such deck"})
    return Deck(**d)


def save_deck(store, deck: Deck) -> Deck:
    deck.updated_at = now_iso()
    store.put("decks", deck.to_doc())
    return deck


def base_deck(store, id_or_slug: str | None) -> dict | None:
    if not id_or_slug:
        return None
    d = store.get("base_decks", id_or_slug)
    if d is None:
        rows = store.find("base_decks", slug=id_or_slug)
        d = rows[0] if rows else None
    return d


BASE_STYLE_PREFIX = {
    "smith1909": "black ink line art with flat watercolour fills on cream paper, single scene inside a thin border, early twentieth-century tarot line art",
    "conver1760": "woodcut line art with flat primary colours (red, blue, yellow, flesh) on cream paper, eighteenth-century Marseille tarot print",
}


def style_from_base(store, base: dict) -> StyleGuide:
    cards = store.find("base_cards", base_deck_id=base["id"])
    cards.sort(key=lambda c: c.get("position_key") or "")
    refs = [ReferenceImage(url=c["image_url"], source="base_card", weight=1.0) for c in cards[:3]]
    prefix = BASE_STYLE_PREFIX.get(base.get("slug", ""), f"in the manner of {base.get('name', 'the base deck')}, public-domain tarot line art")
    line = "woodcut" if "conver" in base.get("slug", "") or "marseille" in base.get("tradition", "").lower() else "ink"
    return StyleGuide(prompt_prefix=prefix, line=line, reference_images=refs)


def symbols_by_position(store, base: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for s in store.find("base_symbols", base_deck_id=base["id"]):
        for pk in s.get("cards", []) or []:
            out.setdefault(pk, []).append(s)
    return out


def _placement_salience(p: str | None) -> float:
    return {"center": 1.0, "top": 0.7, "bottom": 0.7, "left": 0.5, "right": 0.5}.get(p or "any", 0.6)


# ----------------------------------------------------------------------------- create (wizard)
def create_deck(store, storage, user, body: DeckCreate) -> Deck:
    from service import symbols as symbols_svc

    base = base_deck(store, body.origin.base_deck_id) if body.origin.kind == "base" else None
    if body.origin.kind == "base" and base is None:
        raise HTTPException(404, {"code": "not_found", "detail": "no such base deck"})
    if body.origin.kind == "fork":
        src = get_deck(store, body.origin.forked_from_deck_id or "")
        return fork_deck(store, storage, src, user, name=body.name, visibility=body.visibility)
    st_key = body.structure_template_id or (base or {}).get("structure_template_id") or "tarot78"
    st = structure(st_key)
    style = body.style_guide
    if style is None and body.style_from_base_deck_id:
        b2 = base_deck(store, body.style_from_base_deck_id)
        style = style_from_base(store, b2) if b2 else None
    if style is None and base is not None:
        style = style_from_base(store, base)
    deck = Deck(
        id=new_id("d_"), slug=unique_slug(store, body.name), name=body.name.strip(), description=body.description,
        owner_id=user.id, visibility=body.visibility, structure_template_id=st.key, style_guide=style or StyleGuide(),
        origin=body.origin if base is None else body.origin.model_copy(update={"base_deck_id": base["id"]}),
        settings=body.settings or DeckSettings(), share_token=secrets.token_urlsafe(12) if body.visibility == "unlisted" else None,
        base_registry_version=(base or {}).get("registry_version"),
    )
    store.put("decks", deck.to_doc())
    store.put("memberships", Membership(id=new_id("m_"), deck_id=deck.id, user_id=user.id, role="owner").to_doc())
    n_symbols = 0
    if base is not None and body.import_symbols != []:
        n_symbols = len(symbols_svc.import_from_base(store, storage, deck, base["slug"], body.import_symbols, user))
    n_cards = 0
    if base is not None and body.card_mode == "inherit":
        n_cards = inherit_cards(store, deck, base, st, user)
    for inv in body.invites or []:
        if inv.get("email"):
            create_invitation(store, deck, user, email=inv["email"], role=inv.get("role", "member"))
    activity.log(store, deck.id, user.id, "deck.created", {"origin": deck.origin.kind, "base_deck_id": (base or {}).get("id"), "cards": n_cards, "symbols": n_symbols})
    return recompute_stats(store, deck)


def inherit_cards(store, deck: Deck, base: dict, st: StructureTemplate, user) -> int:
    """Base card image → v0 of every matching position (provenance: upload with the base card as reference)."""
    base_cards = store.find("base_cards", base_deck_id=base["id"])
    by_key = {c["position_key"]: c for c in base_cards}
    by_title = {re.sub(r"[^a-z0-9]", "", (c.get("title") or "").lower()): c for c in base_cards}
    mapping = symbols_by_position(store, base)
    deck_symbols = {s["key"]: s for s in store.find("symbols", deck_id=deck.id)}
    n = 0
    positions = st.positions or [Position(key=c["position_key"], title=c.get("title", c["position_key"]), order=i) for i, c in enumerate(base_cards)]
    for pos in positions:
        bc = by_key.get(pos.key) or by_title.get(re.sub(r"[^a-z0-9]", "", pos.title.lower()))
        if bc is None:
            continue
        cid, vid = new_id("c_"), new_id("v_")
        declared, detected = [], []
        for bs in mapping.get(bc["position_key"], []):
            ds = deck_symbols.get(bs["key"])
            if ds is None:
                continue
            placement = bs.get("placement") or "any"
            declared.append(SymbolDeclared(symbol_id=ds["id"], placement=placement if placement != "any" else None))
            detected.append(SymbolDetected(symbol_id=ds["id"], salience=_placement_salience(placement), tagged_by="human", declared_only=True))
        version = Version(id=vid, card_id=cid, deck_id=deck.id, v=0, image_url=bc["image_url"], thumb_url=bc.get("thumb_url"),
                          symbols_declared=declared, symbols_detected=detected, created_by=user.id,
                          how={"kind": "generation", "mode": "upload", "reference_image_url": bc["image_url"], "prompt_user": "",
                               "prompt_full": "", "provider": "base_deck", "model": base.get("slug", ""), "candidates": [], "chosen_index": None,
                               "base_card_id": bc["id"], "caption": bc.get("caption", "")})
        card = Card(id=cid, deck_id=deck.id, position_key=pos.key, title=pos.title, maker_id=user.id, status="draft",
                    current_version_id=vid, branches=[{"branch_key": "main", "head_version_id": vid}], share_token=secrets.token_urlsafe(8))
        store.put("versions", version.to_doc())
        store.put("cards", card.to_doc())
        n += 1
    return n


# ----------------------------------------------------------------------------- read / list / stats
def recompute_stats(store, deck: Deck) -> Deck:
    cards = [c for c in store.find("cards", deck_id=deck.id) if c.get("status") != "archived"]
    st = structures().get(deck.structure_template_id)
    total = len(st.positions) if st and st.positions else None
    filled = len({c["position_key"] for c in cards}) if total else len(cards)
    fids = [v.get("checks", {}).get("fidelity") for v in store.find("versions", deck_id=deck.id)]
    fids = [f for f in fids if isinstance(f, (int, float))]
    symbols = store.find("symbols", deck_id=deck.id, status="active")
    tested = [s for s in symbols if s.get("measured", {}).get("coherence") in ("consistent", "contested")]
    consistent = [s for s in tested if s["measured"]["coherence"] == "consistent"]
    deck.stats.cards = len(cards)
    deck.stats.filled_positions = filled
    deck.stats.total_positions = total
    deck.stats.symbols = len(symbols)
    deck.stats.readings = store.count("readings", deck_id=deck.id)
    deck.stats.sessions = store.count("sessions", deck_id=deck.id)
    deck.stats.forks = len(store.find("decks", **{"origin.forked_from_deck_id": deck.id})) if False else len([d for d in store.all("decks") if (d.get("origin") or {}).get("forked_from_deck_id") == deck.id])
    deck.stats.coherence_index = (len(consistent) / len(tested)) if tested else None
    deck.stats.mean_fidelity = (sum(fids) / len(fids)) if fids else None
    store.put("decks", deck.to_doc())
    return deck


def list_decks(store, user, visibility: str = "public", sort: str = "recent", limit: int = 50) -> list[Deck]:
    rows = store.all("decks")
    out = []
    for d in rows:
        deck = Deck(**d)
        if visibility == "mine":
            if user is None:
                continue
            from service.permissions import role_in_deck
            if not (deck.owner_id == user.id or role_in_deck(store, deck, user) in ("owner", "curator", "member")):
                continue
        elif deck.visibility != visibility:
            continue
        out.append(deck)
    keyf = {
        "recent": lambda d: d.updated_at,
        "cards": lambda d: d.stats.cards,
        "forks": lambda d: d.stats.forks,
        "coherence": lambda d: d.stats.coherence_index if d.stats.coherence_index is not None else -1,
    }.get(sort, lambda d: d.updated_at)
    out.sort(key=keyf, reverse=True)
    return out[:limit]


def update_deck(store, deck: Deck, body: DeckPatch, user, role: str) -> Deck:
    data = body.model_dump(exclude_none=True)
    if role != "owner":
        allowed = {"style_guide", "structure_template_id"}
        if set(data) - allowed:
            raise HTTPException(403, {"code": "role_required", "detail": "only the owner can change these settings"})
    if "structure_template_id" in data:
        structure(data["structure_template_id"])
    if "owner_id" in data and data["owner_id"] != deck.owner_id:
        new_owner = data["owner_id"]
        m = [x for x in store.find("memberships", deck_id=deck.id, user_id=new_owner)]
        if not m:
            raise HTTPException(422, {"code": "validation", "detail": "the new owner must be a member"})
        m[0]["role"] = "owner"; store.put("memberships", m[0])
        old = store.find("memberships", deck_id=deck.id, user_id=deck.owner_id)
        if old:
            old[0]["role"] = "curator"; store.put("memberships", old[0])
        activity.log(store, deck.id, user.id, "deck.transferred", {"to": new_owner})
    if "visibility" in data and data["visibility"] == "unlisted" and not deck.share_token:
        deck.share_token = secrets.token_urlsafe(12)
    updated = Deck(**{**deck.model_dump(), **data})
    if "visibility" in data or "owner_id" in data:
        activity.log(store, deck.id, user.id, "deck.settings", {k: data[k] for k in ("visibility", "owner_id") if k in data})
    return save_deck(store, updated)


DECK_SCOPED = ("memberships", "invitations", "symbols", "symbol_proposals", "cards", "versions", "readings", "sessions",
               "rounds", "activities", "upstream_proposals", "jobs")


def delete_deck(store, deck: Deck) -> None:
    for coll in DECK_SCOPED:
        for d in store.find(coll, deck_id=deck.id):
            store.delete(coll, d["id"])
    store.delete("decks", deck.id)


def lineage(store, deck: Deck) -> dict:
    ancestors, cur, seen = [], deck, set()
    while cur.origin.kind == "fork" and cur.origin.forked_from_deck_id and cur.origin.forked_from_deck_id not in seen:
        seen.add(cur.origin.forked_from_deck_id)
        p = store.get("decks", cur.origin.forked_from_deck_id)
        if p is None:
            break
        cur = Deck(**p)
        ancestors.append({"deck_id": cur.id, "slug": cur.slug, "name": cur.name, "visibility": cur.visibility})
    children = [{"deck_id": d["id"], "slug": d["slug"], "name": d["name"], "visibility": d.get("visibility")}
                for d in store.all("decks") if (d.get("origin") or {}).get("forked_from_deck_id") == deck.id]
    base = base_deck(store, deck.origin.base_deck_id) if deck.origin.kind == "base" else None
    for a in ancestors:
        pass
    return {"deck_id": deck.id, "origin": deck.origin.model_dump(), "base_deck": {"id": base["id"], "slug": base["slug"], "name": base["name"]} if base else None,
            "ancestors": list(reversed(ancestors)), "children": children}


# ----------------------------------------------------------------------------- members & invitations
def list_members(store, deck: Deck) -> list[dict]:
    out = []
    for m in store.find("memberships", deck_id=deck.id):
        u = store.get("users", m["user_id"]) or {}
        out.append({**m, "name": u.get("name"), "email": u.get("email"), "avatar_url": u.get("avatar_url")})
    out.sort(key=lambda m: ({"owner": 0, "curator": 1, "member": 2}.get(m["role"], 3), m.get("joined_at") or ""))
    return out


def add_member(store, deck: Deck, actor, user_id: str | None, email: str | None, role: str) -> dict:
    if role == "owner":
        raise HTTPException(422, {"code": "validation", "detail": "transfer ownership from settings"})
    uid = user_id
    if uid is None and email:
        rows = store.find("users", email=email.strip().lower())
        if not rows:
            inv = create_invitation(store, deck, actor, email=email, role=role)
            return {"invited": True, "invitation": inv}
        uid = rows[0]["id"]
    if uid is None or store.get("users", uid) is None:
        raise HTTPException(404, {"code": "not_found", "detail": "no such user"})
    existing = store.find("memberships", deck_id=deck.id, user_id=uid)
    if existing:
        existing[0]["role"] = role if existing[0]["role"] != "owner" else "owner"
        store.put("memberships", existing[0])
        return existing[0]
    m = Membership(id=new_id("m_"), deck_id=deck.id, user_id=uid, role=role, invited_by=actor.id).to_doc()
    store.put("memberships", m)
    notifications.notify(store, uid, "membership.added", f"You were added to {deck.name} as {role}", deck_id=deck.id)
    activity.log(store, deck.id, actor.id, "member.added", {"user_id": uid, "role": role})
    return m


def set_role(store, deck: Deck, actor, user_id: str, role: str) -> dict:
    if user_id == deck.owner_id:
        raise HTTPException(422, {"code": "validation", "detail": "the owner's role changes only by transfer"})
    rows = store.find("memberships", deck_id=deck.id, user_id=user_id)
    if not rows:
        raise HTTPException(404, {"code": "not_found", "detail": "not a member"})
    rows[0]["role"] = role
    rows[0]["updated_at"] = now_iso()
    store.put("memberships", rows[0])
    activity.log(store, deck.id, actor.id, "member.role", {"user_id": user_id, "role": role})
    return rows[0]


def remove_member(store, deck: Deck, actor, user_id: str) -> None:
    if user_id == deck.owner_id:
        raise HTTPException(422, {"code": "validation", "detail": "the owner cannot be removed"})
    for m in store.find("memberships", deck_id=deck.id, user_id=user_id):
        store.delete("memberships", m["id"])
    activity.log(store, deck.id, actor.id, "member.removed", {"user_id": user_id})


def create_invitation(store, deck: Deck, actor, email: str | None = None, role: str = "member", days: int = 14) -> dict:
    exp = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
    inv = Invitation(id=new_id("i_"), deck_id=deck.id, email=(email or "").strip().lower() or None, link_token=secrets.token_urlsafe(16),
                     role=role if role in ("member", "curator") else "member", expires_at=exp, created_by=actor.id).to_doc()
    store.put("invitations", inv)
    return inv


def accept_invitation(store, token: str, user) -> dict:
    rows = store.find("invitations", link_token=token)
    inv = rows[0] if rows else None
    if inv is None or inv.get("accepted_at"):
        raise HTTPException(404, {"code": "not_found", "detail": "invitation not found or already used"})
    if inv["expires_at"] < now_iso():
        raise HTTPException(410, {"code": "expired", "detail": "invitation expired"})
    if inv.get("email") and user.email and inv["email"] != user.email.lower():
        raise HTTPException(403, {"code": "role_required", "detail": "this invitation was sent to another address"})
    deck = get_deck(store, inv["deck_id"])
    existing = store.find("memberships", deck_id=deck.id, user_id=user.id)
    if not existing:
        store.put("memberships", Membership(id=new_id("m_"), deck_id=deck.id, user_id=user.id, role=inv["role"], invited_by=inv.get("created_by")).to_doc())
    inv["accepted_at"] = now_iso()
    inv["accepted_by"] = user.id
    store.put("invitations", inv)
    activity.log(store, deck.id, user.id, "member.joined", {"role": inv["role"]})
    return {"deck": deck.model_dump(), "role": inv["role"]}


# ----------------------------------------------------------------------------- forks (spec §5.10)
def fork_deck(store, storage, src: Deck, user, name: str | None = None, visibility: str = "private") -> Deck:
    deck = Deck(
        id=new_id("d_"), slug=unique_slug(store, name or f"{src.name} fork"), name=(name or f"{src.name} (fork)").strip(),
        description=src.description, owner_id=user.id, visibility=visibility, structure_template_id=src.structure_template_id,
        style_guide=src.style_guide.model_copy(), settings=src.settings.model_copy(),
        origin=DeckOrigin(kind="fork", forked_from_deck_id=src.id, base_deck_id=src.origin.base_deck_id),
        share_token=secrets.token_urlsafe(12) if visibility == "unlisted" else None,
    )
    store.put("decks", deck.to_doc())
    store.put("memberships", Membership(id=new_id("m_"), deck_id=deck.id, user_id=user.id, role="owner").to_doc())
    id_map: dict[str, str] = {}
    n_sym = 0
    for s in store.find("symbols", deck_id=src.id, status="active"):
        src_sym = Symbol(**s)
        measured = src_sym.measured
        prior = measured.coef if measured.n_readings >= 20 else (src_sym.prior_axes or src_sym.declared_axes)
        new = Symbol(**{**src_sym.model_dump(), "id": new_id("sy_"), "deck_id": deck.id, "origin": "inherited_fork",
                        "inherited_from": {"deck_id": src.id, "symbol_id": src_sym.id}, "prior_axes": prior,
                        "prior_source": "parent_grammar" if measured.n_readings >= 20 else (src_sym.prior_source or "attestation"),
                        "measured": {}, "status": "active", "created_at": now_iso(), "updated_at": now_iso()})
        id_map[src_sym.id] = new.id
        store.put("symbols", new.to_doc())
        n_sym += 1
    n_cards = 0
    for c in store.find("cards", deck_id=src.id):
        if c.get("status") == "archived" or not c.get("current_version_id"):
            continue
        head = store.get("versions", c["current_version_id"])
        if head is None:
            continue
        cid, vid = new_id("c_"), new_id("v_")
        remap = lambda items: [{**x, "symbol_id": id_map[x["symbol_id"]]} for x in items if x.get("symbol_id") in id_map]
        v = {**head, "id": vid, "card_id": cid, "deck_id": deck.id, "v": 0, "branch_key": "main", "base_version_id": head["id"],
             "symbols_declared": remap(head.get("symbols_declared", [])), "symbols_detected": remap(head.get("symbols_detected", [])),
             "created_by": user.id, "created_at": now_iso(), "updated_at": now_iso()}
        card = {**c, "id": cid, "deck_id": deck.id, "maker_id": user.id, "status": "draft" if not c.get("intent") else "reading",
                "current_version_id": vid, "branches": [{"branch_key": "main", "head_version_id": vid}], "edit_requests": [],
                "approved_editors": "*", "share_token": secrets.token_urlsafe(8), "created_at": now_iso(), "updated_at": now_iso()}
        store.put("versions", v)
        store.put("cards", card)
        n_cards += 1
    snap = ForkSnapshot(id=new_id("f_"), source_deck_id=src.id, target_deck_id=deck.id,
                        copied={"symbols": n_sym, "cards": n_cards, "style": True, "structure": True}).to_doc()
    store.put("fork_snapshots", snap)
    deck.origin.forked_at_version_snapshot_id = snap["id"]
    deck.lineage.ancestors = [{"deck_id": src.id, "slug": src.slug, "name": src.name}] + src.lineage.ancestors
    save_deck(store, deck)
    src.lineage.children.append({"deck_id": deck.id, "slug": deck.slug, "name": deck.name})
    save_deck(store, src)
    activity.log(store, src.id, user.id, "deck.forked", {"fork_deck_id": deck.id})
    activity.log(store, deck.id, user.id, "deck.created", {"origin": "fork", "from": src.id, "cards": n_cards, "symbols": n_sym})
    notifications.notify(store, src.owner_id, "fork.created", f"{user.name} forked {src.name}", deck_id=src.id)
    return recompute_stats(store, deck)

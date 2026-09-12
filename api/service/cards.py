"""Cards, versions and the image jobs (spec §3.7, §3.12, §5.4–§5.6, §6.6).

Pure functions over store dicts plus the job runner. Job handlers (`generate`, `edit`, `reinterpret_batch`)
are registered at import; `routers/cards.py` imports this module, so `main.py` registers them by including
the router. Bytes never enter a job payload (the store deep-copies JSON): payloads carry references
(`{"key"} | {"path"} | {"url"} | {"b64"}`) that the handler resolves through the storage service.
"""
from __future__ import annotations

import base64
import io
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

import jobs as J
from auth import new_id
from models import Deck, User, now_iso
from service import activity, measure, notifications
from service import decks as decks_svc
from service.permissions import at_least, is_approved_editor, role_in_deck

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPS = ("add", "remove", "replace", "emphasize", "deemphasize", "reposition", "cosmetic")
EXPERIMENT_OPS = {"add", "remove", "replace", "emphasize", "deemphasize", "reposition"}
GEN_MODES = ("prompt", "reference", "variation", "upload")
RATE_LIMIT_JOBS, RATE_LIMIT_WINDOW_S = 10, 600
CANDIDATE_TTL_DAYS = 7
PLACEMENT_SALIENCE = {"center": 1.0, "top": 0.7, "bottom": 0.7, "left": 0.5, "right": 0.5, "any": 0.6}
NON_QUOTA_PROVIDERS = {"upload", "base_deck", "fork", "seed", "restore"}


class CardError(HTTPException):
    def __init__(self, status: int, code: str, detail: str, **extra: Any):
        super().__init__(status, {"code": code, "detail": detail, **extra})


# ----------------------------------------------------------------------------- helpers
def _deck_dict(deck: Any) -> dict:
    return deck.to_doc() if hasattr(deck, "to_doc") else dict(deck)


def _settings(deck: Any) -> dict:
    d = _deck_dict(deck)
    return dict(d.get("settings") or {})


def _uid(user: Any) -> str | None:
    if user is None:
        return None
    return user.id if hasattr(user, "id") else user.get("id")


def _card_model(card: dict):
    from models import Card

    return Card(**card)


def get_card(store, cid: str) -> dict:
    c = store.get("cards", cid)
    if c is None:
        raise CardError(404, "not_found", "no such card")
    return c


def get_version(store, vid: str) -> dict:
    v = store.get("versions", vid)
    if v is None:
        raise CardError(404, "not_found", "no such version")
    return v


def head_version_id(card: dict, branch_key: str = "main") -> str | None:
    for b in card.get("branches") or []:
        if b.get("branch_key") == branch_key:
            return b.get("head_version_id")
    return card.get("current_version_id") if branch_key == "main" else None


def _set_head(card: dict, branch_key: str, vid: str) -> None:
    branches = card.setdefault("branches", [])
    for b in branches:
        if b.get("branch_key") == branch_key:
            b["head_version_id"] = vid
            break
    else:
        branches.append({"branch_key": branch_key, "head_version_id": vid})
    if branch_key == "main":
        card["current_version_id"] = vid


def active_symbols(store, deck_id: str) -> dict[str, dict]:
    return {s["id"]: s for s in store.find("symbols", deck_id=deck_id) if s.get("status", "active") == "active"}


def registry_for(symbols: dict[str, dict]) -> list[dict]:
    return [{"symbol_id": s["id"], "name": s.get("name"), "gloss": s.get("gloss", "")} for s in symbols.values()]


def _ref_from_url(url: str | None) -> dict | None:
    """An image reference a job payload can carry (no bytes)."""
    if not url:
        return None
    if url.startswith("/media/"):
        return {"key": url[len("/media/"):].split("?")[0]}
    if url.startswith("http"):
        return {"url": url}
    return {"path": url}


def resolve_ref(storage, ref: dict | None) -> bytes | None:
    """Turn a payload reference into bytes. Network refs fail softly (None)."""
    if not ref:
        return None
    if ref.get("b64"):
        try:
            return base64.b64decode(ref["b64"])
        except Exception:
            return None
    if ref.get("key"):
        return storage.get(ref["key"])
    if ref.get("path"):
        p = ref["path"]
        cand = [p, os.path.join(HERE, p.lstrip("/"))]
        for c in cand:
            if os.path.isfile(c):
                with open(c, "rb") as f:
                    return f.read()
        return None
    if ref.get("url"):
        try:
            import httpx

            r = httpx.get(ref["url"], headers={"User-Agent": "pixie/0.5 (datos@corlide.org)"}, timeout=8, follow_redirects=True)
            if r.status_code == 200 and r.content:
                return r.content
        except Exception:
            return None
    return None


def symbol_payload(sym: dict) -> dict:
    ex = sym.get("exemplar") or {}
    return {"symbol_id": sym["id"], "name": sym.get("name"), "gloss": sym.get("gloss", ""), "placement": sym.get("placement") or None,
            "exemplar_ref": _ref_from_url(ex.get("image_url"))}


def _hydrate_symbol(storage, s: dict) -> dict:
    out = {k: v for k, v in s.items() if k != "exemplar_ref"}
    data = resolve_ref(storage, s.get("exemplar_ref"))
    if data:
        out["exemplar_bytes"] = data
    return out


def _style_guide_dict(deck: Any) -> dict:
    sg = _deck_dict(deck).get("style_guide") or {}
    return {k: v for k, v in sg.items() if k != "style_centroid_embedding"}


def _style_ref_refs(store, deck: Any, limit: int = 3) -> list[dict]:
    """Style references by weight, then the deck's landed heads (spec §6.3). References only, no bytes."""
    d = _deck_dict(deck)
    refs = sorted((d.get("style_guide") or {}).get("reference_images") or [], key=lambda r: -float(r.get("weight", 1.0)))
    out = [r for r in (_ref_from_url(x.get("url")) for x in refs) if r]
    if len(out) < limit:
        for c in store.find("cards", deck_id=d["id"], status="landed"):
            v = store.get("versions", c.get("current_version_id") or "")
            r = _ref_from_url((v or {}).get("image_url"))
            if r:
                out.append(r)
            if len(out) >= limit:
                break
    return out[:limit]


def _month_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def generation_usage(store, deck_id: str) -> int:
    """Versions produced by a model this month (uploads, base cards, forks, restores do not count)."""
    n = 0
    for v in store.find("versions", deck_id=deck_id):
        how = v.get("how") or {}
        if v.get("synthetic") or how.get("provider") in NON_QUOTA_PROVIDERS:
            continue
        if (v.get("created_at") or "").startswith(_month_prefix()):
            n += 1
    return n


def check_quota(store, deck: Any, needed: int = 1) -> None:
    quota = int(_settings(deck).get("generation_quota_month", 200))
    used = generation_usage(store, _deck_dict(deck)["id"])
    if used + needed > quota:
        raise CardError(409, "quota_exceeded", f"this deck has used {used} of {quota} generations this month", used=used, quota=quota)


def check_rate(store, user_id: str) -> None:
    limit = int(os.environ.get("PIXIE_RATE_LIMIT_JOBS", RATE_LIMIT_JOBS))  # read per call so tests and admins can raise it
    since = (datetime.now(timezone.utc) - timedelta(seconds=RATE_LIMIT_WINDOW_S)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    recent = [j for j in store.find("jobs", created_by=user_id) if j.get("kind") in ("generate", "edit", "reinterpret_batch") and (j.get("created_at") or "") >= since]
    if len(recent) >= limit:
        raise CardError(429, "rate_limited", f"at most {limit} image jobs per {RATE_LIMIT_WINDOW_S // 60} minutes")


def _embed(text: str) -> list[float] | None:
    try:
        from pixie.embed import embed

        return [float(x) for x in embed([text])[0]]
    except Exception:
        return None


def _validate_axes(axes: Any) -> list[float]:
    try:
        out = [float(a) for a in axes]
    except Exception:
        raise CardError(422, "validation", "axes must be eight numbers")
    if len(out) != 8 or any(a < -3 or a > 3 for a in out):
        raise CardError(422, "validation", "axes must be eight values within -3..3")
    return out


def human_readings(store, version_id: str) -> int:
    return sum(1 for r in store.find("readings", version_id=version_id) if not r.get("synthetic"))


# ----------------------------------------------------------------------------- card CRUD
def next_free_key(store, deck_id: str) -> str:
    keys = [c.get("position_key") or "" for c in store.find("cards", deck_id=deck_id)]
    nums = [int(m.group(1)) for k in keys for m in [re.match(r"free-(\d+)$", k)] if m]
    return f"free-{(max(nums) + 1 if nums else 1):04d}"


def create_card(store, deck: Any, user: Any, body: dict) -> dict:
    d = _deck_dict(deck)
    st = decks_svc.structure(d.get("structure_template_id") or "free")
    pos_key = (body.get("position_key") or "").strip()
    title = (body.get("title") or "").strip()[:80] or None
    if st.key == "free":
        pos_key = pos_key or next_free_key(store, d["id"])
    else:
        pos = next((p for p in st.positions if p.key == pos_key), None)
        if pos is None:
            raise CardError(422, "validation", f"position {pos_key!r} is not in the {st.key} structure")
        title = title or pos.title
    for c in store.find("cards", deck_id=d["id"], position_key=pos_key):
        if c.get("status") != "archived":
            raise CardError(409, "position_taken", f"position {pos_key} already has a card", card_id=c["id"])
    now = now_iso()
    card = {"id": new_id("c_"), "deck_id": d["id"], "position_key": pos_key, "title": title, "maker_id": _uid(user), "intent": None,
            "approved_editors": body.get("approved_editors") or "*", "edit_requests": [], "status": "draft", "current_version_id": None,
            "branches": [], "tags": list(body.get("tags") or []), "share_token": secrets.token_urlsafe(8), "encoder_ids": [_uid(user)],
            "pending_version_id": None, "synthetic": False, "created_at": now, "updated_at": now}
    if body.get("intent"):
        _apply_intent(card, body["intent"])
    store.put("cards", card)
    activity.log(store, d["id"], _uid(user), "card.created", {"card_id": card["id"], "position_key": pos_key})
    return card


def _apply_intent(card: dict, intent: dict) -> None:
    statement = (intent.get("statement") or "").strip()[:140]
    if not statement:
        raise CardError(422, "validation", "the intent needs a statement")
    axes = _validate_axes(intent.get("axes") or [])
    card["intent"] = {"statement": statement, "axes": axes, "embedding": _embed(statement)}


def update_card(store, deck: Any, card: dict, user: Any, body: dict) -> dict:
    if card.get("maker_id") != _uid(user):
        raise CardError(403, "role_required", "only the maker edits the intent, title and access of their card")
    if body.get("intent") is not None:
        _apply_intent(card, body["intent"])
        if card.get("status") == "draft" and card.get("current_version_id"):
            card["status"] = "reading"
    if body.get("title") is not None:
        card["title"] = (body["title"] or "").strip()[:80] or None
    if body.get("approved_editors") is not None:
        ae = body["approved_editors"]
        card["approved_editors"] = "*" if ae == "*" else [str(x) for x in ae]
    if body.get("tags") is not None:
        card["tags"] = [str(t)[:30] for t in body["tags"]][:20]
    card["updated_at"] = now_iso()
    store.put("cards", card)
    return card


def archive_card(store, deck: Any, card: dict, user: Any) -> dict:
    role = role_in_deck(store, deck if hasattr(deck, "to_doc") else Deck(**deck), user)
    if card.get("maker_id") != _uid(user) and not at_least(role, "curator"):
        raise CardError(403, "role_required", "only the maker or a curator archives a card")
    card["status"] = "archived"
    card["updated_at"] = now_iso()
    store.put("cards", card)
    activity.log(store, card["deck_id"], _uid(user), "card.archived", {"card_id": card["id"]})
    return card


def create_edit_request(store, deck: Any, card: dict, user: Any, note: str) -> dict:
    uid = _uid(user)
    if uid == card.get("maker_id"):
        raise CardError(422, "validation", "you are the maker of this card")
    for r in card.get("edit_requests") or []:
        if r.get("user_id") == uid and r.get("status") == "open":
            raise CardError(409, "duplicate", "you already have an open request on this card")
    req = {"id": new_id("er_"), "user_id": uid, "note": (note or "")[:140], "status": "open", "created_at": now_iso()}
    card.setdefault("edit_requests", []).append(req)
    card["updated_at"] = now_iso()
    store.put("cards", card)
    if card.get("maker_id"):
        notifications.notify(store, card["maker_id"], "edit_request.received", f"{getattr(user, 'name', 'someone')} asks to edit your card {card.get('title') or card.get('position_key')}: {req['note']}", card["deck_id"], card["id"])
    return req


def decide_edit_request(store, deck: Any, card: dict, user: Any, rid: str, action: str) -> dict:
    if card.get("maker_id") != _uid(user):
        raise CardError(403, "role_required", "only the maker approves editors on their card")
    req = next((r for r in card.get("edit_requests") or [] if r.get("id") == rid), None)
    if req is None:
        raise CardError(404, "not_found", "no such request")
    if req.get("status") != "open":
        raise CardError(409, "already_decided", "this request was already decided")
    if action not in ("approve", "decline"):
        raise CardError(422, "validation", "action must be approve or decline")
    req["status"] = "approved" if action == "approve" else "declined"
    req["decided_at"] = now_iso()
    if action == "approve":
        ae = card.get("approved_editors", "*")
        policy = _settings(deck).get("default_editor_policy", "any_member")
        if isinstance(ae, list):
            if req["user_id"] not in ae:
                ae.append(req["user_id"])
        elif policy != "any_member":
            card["approved_editors"] = [req["user_id"]]
    card["updated_at"] = now_iso()
    store.put("cards", card)
    notifications.notify(store, req["user_id"], f"edit_request.{req['status']}", f"your request to edit {card.get('title') or card.get('position_key')} was {req['status']}", card["deck_id"], card["id"])
    return req


# ----------------------------------------------------------------------------- versions: build & attach
def _version_from_candidate(storage, version: dict, cand: dict, index: int) -> None:
    version["image_url"] = storage.url(cand["image_key"]) if cand.get("image_key") else cand.get("image_url")
    version["thumb_url"] = storage.url(cand["thumb_key"]) if cand.get("thumb_key") else cand.get("thumb_url")
    version["width"], version["height"] = cand.get("width"), cand.get("height")
    version["symbols_detected"] = [{"symbol_id": x["symbol_id"], "salience": float(x.get("salience", 0.6)), "bbox": x.get("bbox"),
                                    "tagged_by": "human" if x.get("tagged_by") in ("human", "declared_only") else "vision",
                                    "declared_only": x.get("tagged_by") == "declared_only"} for x in cand.get("symbols_detected") or []]
    version["checks"] = {"fidelity": cand.get("fidelity"), "containment": cand.get("containment"), "style_score": cand.get("style_score"),
                         "symbols_missing": list(cand.get("symbols_missing") or []), "also_detected": list(cand.get("also_detected") or []),
                         "safety": "ok", "detect_backend": cand.get("backend")}
    version["how"]["chosen_index"] = index
    version["status"] = "chosen"


def _public_candidates(storage, cands: list[dict]) -> list[dict]:
    out = []
    for c in cands:
        out.append({"index": c.get("index"), "image_url": storage.url(c["image_key"]) if c.get("image_key") else c.get("image_url"),
                    "thumb_url": storage.url(c["thumb_key"]) if c.get("thumb_key") else c.get("thumb_url"),
                    "heatmap_url": storage.url(c["heatmap_key"]) if c.get("heatmap_key") else c.get("heatmap_url"),
                    "width": c.get("width"), "height": c.get("height"), "style_score": c.get("style_score"), "fidelity": c.get("fidelity"),
                    "containment": c.get("containment"), "embed_cos": c.get("embed_cos"), "ssim_out": c.get("ssim_out"),
                    "below_threshold": c.get("below_threshold", False), "attempt": c.get("attempt"), "preserve": c.get("preserve"),
                    "symbols_detected": c.get("symbols_detected") or [], "symbols_missing": c.get("symbols_missing") or [],
                    "also_detected": c.get("also_detected") or [], "backend": c.get("backend")})
    return out


def _attach_version(store, storage, deck_d: dict, card: dict, version: dict, user_id: str | None) -> dict:
    """Make `version` the head of its branch and move the card through §3.12."""
    branch = version.get("branch_key") or "main"
    is_edit = version.get("how", {}).get("kind") == "edit" or bool(version.get("how", {}).get("op"))
    _set_head(card, branch, version["id"])
    card["pending_version_id"] = None
    card["pending_job_id"] = None
    if branch == "main":
        if is_edit:
            if card.get("status") in ("open", "reading", "draft"):
                card["status"] = "reading"
            card["n_versions"] = int(card.get("n_versions", 1)) + 1
            editor = (version.get("how") or {}).get("editor_id")
            if editor and editor not in (card.get("encoder_ids") or []):
                card.setdefault("encoder_ids", []).append(editor)
        else:
            if card.get("status") == "draft" and (card.get("intent") or {}).get("statement"):
                card["status"] = "reading"
            card["n_versions"] = 1
    card["updated_at"] = now_iso()
    store.put("cards", card)
    version["updated_at"] = now_iso()
    store.put("versions", version)
    measure.invalidate(deck_d["id"])
    activity.log(store, deck_d["id"], user_id, "card.version_created", {"card_id": card["id"], "version_id": version["id"], "v": version.get("v"),
                                                                        "branch_key": branch, "op": (version.get("how") or {}).get("op"), "mode": (version.get("how") or {}).get("mode")})
    if is_edit and branch == "main":
        _notify_readers(store, deck_d, card, version)
    if card.get("status") in ("landed",) or not (deck_d.get("style_guide") or {}).get("style_centroid_embedding"):
        try:
            recompute_style_centroid(store, storage, deck_d)
        except Exception as e:  # never block on the centroid
            print(f"[cards] style centroid skipped: {e}")
    return version


def _notify_readers(store, deck_d: dict, card: dict, version: dict) -> None:
    editor = (version.get("how") or {}).get("editor_id")
    text = f"{card.get('title') or card.get('position_key')} has a new version (v{version.get('v')}) to read"
    for m in store.find("memberships", deck_id=deck_d["id"]):
        if m.get("user_id") and m["user_id"] != editor and at_least(m.get("role", "member"), "member"):
            notifications.notify(store, m["user_id"], "card.needs_reading", text, deck_d["id"], card["id"])


def choose_candidate(store, storage, deck: Any, card: dict, version: dict, user: Any, index: int) -> dict:
    d = _deck_dict(deck)
    if version.get("status") != "candidates":
        raise CardError(409, "already_chosen", "this version already has its image")
    if version.get("created_by") != _uid(user):
        raise CardError(403, "role_required", "only the person who ran the job picks its candidate")
    cands = (version.get("how") or {}).get("candidates") or []
    cand = next((c for c in cands if int(c.get("index", -1)) == int(index)), None)
    if cand is None:
        raise CardError(422, "validation", f"no candidate with index {index}")
    _version_from_candidate(storage, version, cand, int(index))
    for c in cands:
        c["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=CANDIDATE_TTL_DAYS)).isoformat(timespec="seconds").replace("+00:00", "Z") if int(c.get("index", -1)) != int(index) else None
    return _attach_version(store, storage, d, card, version, _uid(user))


# ----------------------------------------------------------------------------- generate (§5.4)
def _new_version_doc(deck_id: str, card: dict, branch_key: str, base_version_id: str | None, v: int, how: dict, user_id: str | None) -> dict:
    now = now_iso()
    return {"id": new_id("v_"), "card_id": card["id"], "deck_id": deck_id, "v": v, "branch_key": branch_key, "base_version_id": base_version_id,
            "image_url": "", "thumb_url": None, "width": None, "height": None, "symbols_declared": [], "symbols_detected": [], "how": how,
            "checks": {"style_score": None, "symbols_missing": [], "safety": "ok"}, "status": "candidates", "created_by": user_id,
            "synthetic": False, "created_at": now, "updated_at": now}


def _resolve_generation_target(store, deck: Any, card: dict, user: Any, body: dict) -> tuple[str, str | None, int]:
    """Where a generation lands: v0 on main while the card is a draft; otherwise a new branch (curator, allow_branches)."""
    if card.get("status") == "draft":
        return "main", None, 0
    role = role_in_deck(store, deck if hasattr(deck, "to_doc") else Deck(**deck), user)
    if not (at_least(role, "curator") and _settings(deck).get("allow_branches", True)):
        raise CardError(409, "card_not_draft", "this card already has a v0; curators may generate into a new branch")
    key = (body.get("branch_key") or f"gen-{secrets.token_hex(2)}")[:24]
    head = card.get("current_version_id")
    base = store.get("versions", head) if head else None
    return key, head, int((base or {}).get("v", 0)) + 1


def start_generate(store, jobs, storage, deck: Any, card: dict, user: Any, body: dict) -> dict:
    d = _deck_dict(deck)
    uid = _uid(user)
    if card.get("maker_id") != uid and not at_least(role_in_deck(store, deck if hasattr(deck, "to_doc") else Deck(**deck), user), "curator"):
        raise CardError(403, "role_required", "only the maker (or a curator) generates images for this card")
    mode = body.get("mode") or "prompt"
    if mode not in GEN_MODES:
        raise CardError(422, "validation", f"mode must be one of {GEN_MODES}")
    symbols = active_symbols(store, d["id"])
    chosen_ids = [s for s in (body.get("symbols") or []) if s in symbols]
    unknown = [s for s in (body.get("symbols") or []) if s not in symbols]
    if unknown:
        raise CardError(422, "validation", f"symbols not in this deck's registry: {unknown} — propose them first")
    branch_key, base_version_id, v = _resolve_generation_target(store, deck, card, user, body)
    settings = _settings(deck)

    if mode == "upload":
        if not body.get("rights_attested"):
            raise CardError(422, "validation", "uploads need the rights attestation")
        raw = body.get("image_base64") or ""
        try:
            data = base64.b64decode(raw.split(",")[-1])
            from PIL import Image

            im = Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            raise CardError(422, "validation", "image_base64 must be a valid PNG/JPEG/WebP")
        key = f"decks/{d['id']}/cards/{card['id']}/upload_{secrets.token_hex(4)}.png"
        buf = io.BytesIO()
        im.save(buf, "PNG")
        storage.put(key, buf.getvalue(), "image/png")
        tb = im.copy()
        tb.thumbnail((400, 400 * 10))
        tbuf = io.BytesIO()
        tb.save(tbuf, "WEBP", quality=82)
        tkey = storage.put(key.replace(".png", ".webp"), tbuf.getvalue(), "image/webp")
        declared = [{"symbol_id": s, "placement": symbols[s].get("placement") if symbols[s].get("placement") != "any" else None} for s in chosen_ids]
        rec = _reconcile(buf.getvalue(), symbols, declared)
        how = {"kind": "generation", "mode": "upload", "reference_image_url": None, "prompt_user": "", "prompt_full": "", "provider": "upload",
               "model": "", "seed": None, "candidates": [], "chosen_index": 0, "rights_attested": True}
        version = _new_version_doc(d["id"], card, branch_key, base_version_id, v, how, uid)
        version["symbols_declared"] = declared
        _version_from_candidate(storage, version, {"image_key": key, "thumb_key": tkey, "width": im.width, "height": im.height,
                                                   "style_score": _style_score_of(store, storage, d, buf.getvalue()), **rec}, 0)
        _attach_version(store, storage, d, card, version, uid)
        return {"version": version, "job": None}

    if not chosen_ids:
        raise CardError(422, "validation", "pick at least one symbol from the registry")
    n = max(1, min(4, int(body.get("n") or settings.get("candidates_per_generation", 2))))
    check_quota(store, deck, n)
    check_rate(store, uid)
    st = decks_svc.structures().get(d.get("structure_template_id") or "free")
    pos_title = card.get("title") or next((p.title for p in (st.positions if st else []) if p.key == card.get("position_key")), None)
    from pixie.imaging.prompts import strip_denylist

    prompt_user = strip_denylist(body.get("prompt_user") or "")
    style_refs = _style_ref_refs(store, deck)
    reference_ref, reference_url = None, None
    if mode == "reference":
        ref = body.get("reference") or {}
        if ref.get("base_card_id"):
            bc = store.get("base_cards", ref["base_card_id"])
            if bc is None:
                raise CardError(404, "not_found", "no such base card")
            reference_url = bc.get("image_url")
        elif ref.get("version_id"):
            reference_url = get_version(store, ref["version_id"]).get("image_url")
        elif ref.get("card_id"):
            rc = get_card(store, ref["card_id"])
            reference_url = get_version(store, rc["current_version_id"]).get("image_url") if rc.get("current_version_id") else None
        elif ref.get("image_base64"):
            reference_ref = {"b64": ref["image_base64"].split(",")[-1]}
        reference_ref = reference_ref or _ref_from_url(reference_url)
        if reference_ref is None:
            raise CardError(422, "validation", "reference mode needs a base card, a card, a version, or an uploaded image")
        strength = float(body.get("strength") or 0.6)
        prompt_user = f"Reinterpret the reference card, keeping its composition (strength {strength:.1f}). {prompt_user}".strip()
    elif mode == "variation":
        cur = store.get("versions", card.get("current_version_id") or "")
        if not cur or not cur.get("image_url"):
            raise CardError(409, "card_not_draft", "variation needs a current version")
        reference_ref = _ref_from_url(cur["image_url"])
        prompt_user = f"A variation of the reference card, same subject and style. {prompt_user}".strip()
    if reference_ref:
        style_refs = [reference_ref] + style_refs[:2]
    how = {"kind": "generation", "mode": mode, "reference_image_url": reference_url, "prompt_user": prompt_user, "prompt_full": "",
           "provider": settings.get("provider") or "", "model": "", "seed": body.get("seed"), "candidates": [], "chosen_index": None}
    version = _new_version_doc(d["id"], card, branch_key, base_version_id, v, how, uid)
    version["symbols_declared"] = [{"symbol_id": s, "placement": symbols[s].get("placement") if symbols[s].get("placement") != "any" else None} for s in chosen_ids]
    store.put("versions", version)
    payload = {"deck_id": d["id"], "card_id": card["id"], "version_id": version["id"], "user_id": uid,
               "imaging": {"provider": settings.get("provider") or None, "style_guide": _style_guide_dict(deck), "position_title": pos_title,
                           "symbols": [symbol_payload(symbols[s]) for s in chosen_ids], "prompt_user": prompt_user,
                           "aspect": (d.get("style_guide") or {}).get("aspect") or "2.75x4.75", "n": n, "seed": body.get("seed"),
                           "style_refs": style_refs, "style_centroid": (d.get("style_guide") or {}).get("style_centroid_embedding"),
                           "registry": registry_for(symbols), "storage_prefix": f"decks/{d['id']}/cards/{card['id']}/gen_{version['id']}"}}
    job = jobs.enqueue("generate", payload, created_by=uid, deck_id=d["id"])
    card["pending_version_id"] = version["id"]
    card["pending_job_id"] = job["id"]
    card["updated_at"] = now_iso()
    store.put("cards", card)
    return {"job": J.public_job(job), "version_id": version["id"]}


def _reconcile(image_bytes: bytes, symbols: dict[str, dict], declared: list[dict]) -> dict:
    try:
        from pixie.imaging.detect import detect_symbols, reconcile

        return reconcile(declared, detect_symbols(image_bytes, registry_for(symbols), declared))
    except Exception:
        return {"symbols_detected": [{"symbol_id": x["symbol_id"], "salience": PLACEMENT_SALIENCE.get(x.get("placement") or "any", 0.6), "bbox": None, "tagged_by": "declared_only"} for x in declared],
                "symbols_missing": [x["symbol_id"] for x in declared], "also_detected": [], "backend": "declared_only"}


def _style_score_of(store, storage, deck_d: dict, image_bytes: bytes) -> float | None:
    centroid = (deck_d.get("style_guide") or {}).get("style_centroid_embedding")
    if not centroid:
        return None
    try:
        from pixie.imaging.style import style_score

        return style_score(image_bytes, centroid)
    except Exception:
        return None


@J.register("generate")
def _job_generate(ctx: J.JobContext):
    store, storage = ctx.store, ctx.services.get("storage")
    imaging = ctx.services.get("imaging")
    if imaging is None or storage is None:
        raise J.NonRetryable("imaging pipeline or storage not available")
    p = ctx.payload
    version = store.get("versions", p["version_id"])
    card = store.get("cards", p["card_id"])
    if version is None or card is None:
        raise J.NonRetryable("card or version vanished")
    im = dict(p["imaging"])
    im["symbols"] = [_hydrate_symbol(storage, s) for s in im.get("symbols") or []]
    im["style_refs"] = [b for b in (resolve_ref(storage, r) for r in im.get("style_refs") or []) if b]
    ctx.progress(0.05, "preparing")
    result = imaging.run_generate(im, {"storage_put": storage.put, "progress": ctx.progress})
    how = version["how"]
    how.update({"prompt_full": result.get("prompt_full", ""), "provider": result.get("provider", ""), "model": result.get("model", ""),
                "seed": result.get("seed"), "candidates": result.get("candidates") or [], "image_embed_backend": result.get("image_embed_backend")})
    if result.get("blocked"):
        version["status"] = "blocked"
        version["checks"]["safety"] = "blocked"
        version["checks"]["safety_reason"] = result.get("reason")
        store.put("versions", version)
        if p.get("user_id"):
            notifications.notify(store, p["user_id"], "generation.blocked", f"a generation was blocked: {result.get('reason')}", p["deck_id"], card["id"])
        return {"version_id": version["id"], "blocked": True, "reason": result.get("reason"), "candidates": 0}
    version["updated_at"] = now_iso()
    store.put("versions", version)
    if p.get("user_id"):
        notifications.notify(store, p["user_id"], "generation.ready", f"{len(how['candidates'])} candidate(s) ready for {card.get('title') or card.get('position_key')}", p["deck_id"], card["id"])
    return {"version_id": version["id"], "candidates": len(how["candidates"]), "provider": result.get("provider"), "elapsed_s": result.get("elapsed_s")}


# ----------------------------------------------------------------------------- edit (§5.5)
def _validate_region(region: Any) -> dict | None:
    if region is None:
        return None
    try:
        r = {k: float(region[k]) for k in ("x", "y", "w", "h")}
    except Exception:
        raise CardError(422, "validation", "region needs x, y, w, h in 0..1")
    if r["w"] <= 0 or r["h"] <= 0 or r["x"] < 0 or r["y"] < 0 or r["x"] + r["w"] > 1.0001 or r["y"] + r["h"] > 1.0001:
        raise CardError(422, "validation", "region must lie inside the image")
    return r


def start_edit(store, jobs, deck: Any, card: dict, user: Any, body: dict) -> dict:
    """Validate one operation, check the lock, enqueue the edit job. Bytes are loaded by the handler."""
    d = _deck_dict(deck)
    deck_m = deck if hasattr(deck, "to_doc") else Deck(**deck)
    uid = _uid(user)
    settings = _settings(deck)
    role = role_in_deck(store, deck_m, user)
    branch_key = (body.get("branch_key") or "main")[:24]
    in_session = bool(body.get("session_id"))
    status = card.get("status")
    if status == "archived":
        raise CardError(409, "card_closed", "this card is archived")
    if status != "open" and not in_session:
        if status == "reading" and at_least(role, "curator") and settings.get("allow_branches", True):
            if branch_key == "main":
                branch_key = f"br-{secrets.token_hex(2)}"
        else:
            raise CardError(409, "card_not_open", f"this card is {status}; it opens after enough readings, or when the maker opens it for edits")
    if not is_approved_editor(store, _card_model(card), deck_m, user) and not (at_least(role, "curator") and branch_key != "main"):
        raise CardError(403, "role_required", "the maker has not approved you as an editor of this card")
    op = body.get("op")
    if op not in OPS:
        raise CardError(422, "validation", f"op must be one of {OPS}")
    symbols = active_symbols(store, d["id"])
    sid, tid = body.get("symbol_id"), body.get("to_symbol_id")
    if op != "cosmetic":
        if not sid or sid not in symbols:
            raise CardError(422, "validation", "symbol_id must be an active symbol of this deck")
        if op == "replace" and (not tid or tid not in symbols):
            raise CardError(422, "validation", "replace needs to_symbol_id from the registry")
        if body.get("bet_axis") is None:
            raise CardError(422, "validation", "experiments need a bet_axis (0..7)")
        bet = int(body["bet_axis"])
        if not 0 <= bet <= 7:
            raise CardError(422, "validation", "bet_axis must be 0..7")
    else:
        bet = None
        if sid or tid:
            raise CardError(422, "validation", "a cosmetic edit changes no symbol")
    rationale = (body.get("rationale") or "").strip()[:140]
    if not rationale and not in_session:
        raise CardError(422, "validation", "a rationale is required (≤ 140 characters)")
    head = head_version_id(card, branch_key) or card.get("current_version_id")
    if branch_key != "main" and head_version_id(card, branch_key) is None:
        head = body.get("base_version_id") or card.get("current_version_id")  # a new branch starts from the given version
    if not head:
        raise CardError(409, "card_not_open", "this card has no version to edit yet")
    if body.get("base_version_id") and body["base_version_id"] != head:
        raise CardError(409, "version_stale", "someone edited first — read the new head", head_version_id=head)
    base = get_version(store, head)
    if not base.get("image_url"):
        raise CardError(409, "version_stale", "the base version has no image yet", head_version_id=head)
    base_declared = [{"symbol_id": x["symbol_id"], "placement": x.get("placement")} for x in base.get("symbols_declared") or []]
    if op in ("remove", "replace", "emphasize", "deemphasize", "reposition") and sid not in {x["symbol_id"] for x in base_declared} | {x["symbol_id"] for x in base.get("symbols_detected") or []}:
        raise CardError(422, "validation", "that symbol is not on the card")
    if op == "add" and sid in {x["symbol_id"] for x in base_declared}:
        raise CardError(422, "validation", "that symbol is already on the card")
    region = _validate_region(body.get("region"))
    target_region = _validate_region(body.get("target_region"))
    how_text = body.get("how_text") or ""
    if op != "cosmetic":
        from pixie.imaging.prompts import validate_how_text

        try:
            validate_how_text(how_text, [symbols[s]["name"] for s in (sid, tid) if s], [s.get("name") for s in symbols.values()])
        except ValueError as e:
            raise CardError(422, "validation", str(e))
    n = max(1, min(4, int(body.get("n") or settings.get("candidates_per_generation", 2))))
    check_quota(store, deck, n)
    check_rate(store, uid)
    how = {"kind": "edit", "op": op, "symbol_id": sid, "to_symbol_id": tid, "region": region, "prompt_user": how_text or None, "prompt_full": "",
           "provider": settings.get("provider") or "", "model": "", "seed": body.get("seed"), "candidates": [], "chosen_index": None,
           "bet_axis": bet, "rationale": rationale, "editor_id": uid, "counts_as_experiment": op in EXPERIMENT_OPS,
           "placement": body.get("placement"), "target_region": target_region, "target_placement": body.get("target_placement")}
    version = _new_version_doc(d["id"], card, branch_key, base["id"], int(base.get("v", 0)) + 1, how, uid)
    version["symbols_declared"] = base_declared  # replaced by declared_after when a candidate is chosen
    store.put("versions", version)
    payload = {"deck_id": d["id"], "card_id": card["id"], "version_id": version["id"], "base_version_id": base["id"], "user_id": uid,
               "auto_choose": bool(body.get("auto_choose")), "session_id": body.get("session_id"),
               "imaging": {"provider": settings.get("provider") or None, "base_image": _ref_from_url(base["image_url"]), "op": op,
                           "symbol": symbol_payload(symbols[sid]) if sid else None, "to_symbol": symbol_payload(symbols[tid]) if tid else None,
                           "region": region, "placement": body.get("placement") or (symbols[sid].get("placement") if sid and symbols[sid].get("placement") != "any" else None),
                           "target_region": target_region, "target_placement": body.get("target_placement"), "how_text": how_text, "n": n,
                           "seed": body.get("seed"), "fidelity_threshold": float(settings.get("fidelity_threshold", 0.85)),
                           "strength": float(body.get("strength") or 1.0), "style_guide": _style_guide_dict(deck), "style_refs": _style_ref_refs(store, deck),
                           "style_centroid": (d.get("style_guide") or {}).get("style_centroid_embedding"), "registry": registry_for(symbols),
                           "declared": base_declared, "storage_prefix": f"decks/{d['id']}/cards/{card['id']}/edit_{version['id']}"}}
    idem = J.idempotency_key(base["id"], op, sid, tid, region, how_text, n, body.get("seed"), uid)
    job = jobs.enqueue("edit", payload, created_by=uid, deck_id=d["id"], idempotency_key=idem)
    card["pending_version_id"] = version["id"]
    card["pending_job_id"] = job["id"]
    card["updated_at"] = now_iso()
    store.put("cards", card)
    return {"job": J.public_job(job), "version_id": version["id"], "base_version_id": base["id"], "branch_key": branch_key}


@J.register("edit")
def _job_edit(ctx: J.JobContext):
    store, storage = ctx.store, ctx.services.get("storage")
    imaging = ctx.services.get("imaging")
    if imaging is None or storage is None:
        raise J.NonRetryable("imaging pipeline or storage not available")
    p = ctx.payload
    version = store.get("versions", p["version_id"])
    card = store.get("cards", p["card_id"])
    deck_d = store.get("decks", p["deck_id"])
    if version is None or card is None or deck_d is None:
        raise J.NonRetryable("card, version or deck vanished")
    im = dict(p["imaging"])
    base_bytes = resolve_ref(storage, im.get("base_image"))
    if base_bytes is None:
        raise J.NonRetryable("the base image could not be loaded")
    im["base_image"] = base_bytes
    im["symbol"] = _hydrate_symbol(storage, im["symbol"]) if im.get("symbol") else None
    im["to_symbol"] = _hydrate_symbol(storage, im["to_symbol"]) if im.get("to_symbol") else None
    im["style_refs"] = [b for b in (resolve_ref(storage, r) for r in im.get("style_refs") or []) if b]
    ctx.progress(0.05, "preparing")
    try:
        result = imaging.run_edit(im, {"storage_put": storage.put, "progress": ctx.progress})
    except ValueError as e:
        raise J.NonRetryable(str(e))
    how = version["how"]
    how.update({"prompt_full": result.get("prompt_full", ""), "provider": result.get("provider", ""), "model": result.get("model", ""),
                "seed": result.get("seed"), "candidates": result.get("candidates") or [], "retries": result.get("retries", 0),
                "expected_region": result.get("expected_region"), "declared_after": result.get("declared_after") or [],
                "fidelity_threshold": result.get("fidelity_threshold"), "image_embed_backend": result.get("image_embed_backend"),
                "counts_as_experiment": bool(result.get("counts_as_experiment", how.get("op") in EXPERIMENT_OPS))})
    if result.get("blocked") or not how["candidates"]:
        version["status"] = "blocked"
        version["checks"]["safety"] = "blocked"
        version["checks"]["safety_reason"] = result.get("blocked") or "no candidates"
        store.put("versions", version)
        if p.get("user_id"):
            notifications.notify(store, p["user_id"], "edit.blocked", f"the edit was blocked: {version['checks']['safety_reason']}", p["deck_id"], card["id"])
        return {"version_id": version["id"], "blocked": True, "candidates": 0}
    version["symbols_declared"] = [{"symbol_id": x["symbol_id"], "placement": x.get("placement")} for x in how["declared_after"]]
    version["updated_at"] = now_iso()
    store.put("versions", version)
    out = {"version_id": version["id"], "candidates": len(how["candidates"]), "best_fidelity": how["candidates"][0].get("fidelity"),
           "retries": how["retries"], "provider": result.get("provider")}
    if p.get("auto_choose"):
        best = how["candidates"][0]
        _version_from_candidate(storage, version, best, int(best.get("index", 0)))
        _attach_version(store, storage, deck_d, card, version, p.get("user_id"))
        out["chosen_index"] = int(best.get("index", 0))
        if p.get("session_id"):
            try:
                from service import sessions as S

                s = store.get("sessions", p["session_id"])
                if s is not None:
                    S.attach_edit(store, deck_d, s, version)
            except Exception as e:
                print(f"[cards] session attach failed: {e}")
    elif p.get("user_id"):
        notifications.notify(store, p["user_id"], "edit.ready", f"{len(how['candidates'])} edit candidate(s) ready (best fidelity {out['best_fidelity']:.2f})", p["deck_id"], card["id"])
    return out


# ----------------------------------------------------------------------------- restore, branches, compare, listing
def restore(store, storage, deck: Any, card: dict, version: dict, user: Any, note: str) -> dict:
    d = _deck_dict(deck)
    uid = _uid(user)
    deck_m = deck if hasattr(deck, "to_doc") else Deck(**deck)
    if not (is_approved_editor(store, _card_model(card), deck_m, user) or card.get("maker_id") == uid or at_least(role_in_deck(store, deck_m, user), "curator")):
        raise CardError(403, "role_required", "restoring needs edit rights on this card")
    if not version.get("image_url"):
        raise CardError(409, "version_stale", "that version has no image")
    branch = version.get("branch_key") or "main"
    head_id = head_version_id(card, branch) or card.get("current_version_id")
    head = store.get("versions", head_id) if head_id else None
    how = {"kind": "edit", "op": "cosmetic", "symbol_id": None, "to_symbol_id": None, "region": None, "prompt_user": None,
           "prompt_full": f"restore {version['id']}", "provider": "restore", "model": "", "seed": None, "candidates": [], "chosen_index": 0,
           "bet_axis": None, "rationale": (note or f"restored v{version.get('v')}")[:140], "editor_id": uid, "counts_as_experiment": False,
           "restored_from_version_id": version["id"]}
    nv = _new_version_doc(d["id"], card, branch, head_id, int((head or version).get("v", 0)) + 1, how, uid)
    nv.update({"image_url": version["image_url"], "thumb_url": version.get("thumb_url"), "width": version.get("width"), "height": version.get("height"),
               "symbols_declared": version.get("symbols_declared") or [], "symbols_detected": version.get("symbols_detected") or [],
               "checks": {**(version.get("checks") or {}), "fidelity": 1.0, "containment": 1.0}, "status": "chosen"})
    return _attach_version(store, storage, d, card, nv, uid)


def create_branch(store, deck: Any, card: dict, user: Any, from_version_id: str | None, branch_key: str | None) -> dict:
    deck_m = deck if hasattr(deck, "to_doc") else Deck(**deck)
    if not at_least(role_in_deck(store, deck_m, user), "curator"):
        raise CardError(403, "role_required", "curators open branches")
    if not _settings(deck).get("allow_branches", True):
        raise CardError(403, "role_required", "this deck does not allow branches")
    src = get_version(store, from_version_id or card.get("current_version_id") or "")
    key = re.sub(r"[^a-z0-9-]", "", (branch_key or f"br-{secrets.token_hex(2)}").lower())[:24] or f"br-{secrets.token_hex(2)}"
    if key == "main" or any(b.get("branch_key") == key for b in card.get("branches") or []):
        raise CardError(409, "duplicate", f"branch {key} exists")
    card.setdefault("branches", []).append({"branch_key": key, "head_version_id": src["id"]})
    card["updated_at"] = now_iso()
    store.put("cards", card)
    activity.log(store, card["deck_id"], _uid(user), "card.branch_created", {"card_id": card["id"], "branch_key": key, "from_version_id": src["id"]})
    return card


def compare(store, storage, v1: dict, v2: dict) -> dict:
    from pixie.imaging.fidelity import diff_heatmap, fidelity

    a, b = resolve_ref(storage, _ref_from_url(v1.get("image_url"))), resolve_ref(storage, _ref_from_url(v2.get("image_url")))
    if a is None or b is None:
        raise CardError(409, "version_stale", "one of the versions has no readable image")
    region = (v2.get("how") or {}).get("expected_region") or (v2.get("how") or {}).get("region")
    parts = fidelity(a, b, region)
    key = f"decks/{v1['deck_id']}/cards/{v1['card_id']}/compare_{v1['id']}_{v2['id']}.png"
    if not storage.exists(key):
        storage.put(key, diff_heatmap(a, b), "image/png")
    return {"a": v1["id"], "b": v2["id"], **parts, "region": region, "heatmap_url": storage.url(key)}


def list_versions(store, card: dict) -> dict:
    vs = sorted(store.find("versions", card_id=card["id"]), key=lambda v: (v.get("created_at") or "", int(v.get("v", 0))))
    out, edges = [], []
    for v in vs:
        how = v.get("how") or {}
        out.append({"id": v["id"], "v": int(v.get("v", 0)), "branch_key": v.get("branch_key", "main"), "base_version_id": v.get("base_version_id"),
                    "image_url": v.get("image_url") or None, "thumb_url": v.get("thumb_url"), "status": v.get("status", "chosen"),
                    "how": {k: how.get(k) for k in ("kind", "mode", "op", "symbol_id", "to_symbol_id", "bet_axis", "rationale", "editor_id", "counts_as_experiment", "provider", "model", "chosen_index")},
                    "checks": v.get("checks") or {}, "symbols_declared": v.get("symbols_declared") or [], "symbols_detected": v.get("symbols_detected") or [],
                    "n_readings": human_readings(store, v["id"]), "created_by": v.get("created_by"), "created_at": v.get("created_at"),
                    "is_head": any(b.get("head_version_id") == v["id"] for b in card.get("branches") or []) or card.get("current_version_id") == v["id"]})
        if v.get("base_version_id"):
            edges.append({"from": v["base_version_id"], "to": v["id"]})
    return {"card_id": card["id"], "versions": out, "edges": edges, "branches": card.get("branches") or []}


# ----------------------------------------------------------------------------- style centroid (§6.3)
def recompute_style_centroid(store, storage, deck: Any) -> list[float] | None:
    from pixie.imaging.fidelity import image_embed, image_embed_backend

    d = _deck_dict(deck)
    imgs: list[bytes] = []
    for r in (d.get("style_guide") or {}).get("reference_images") or []:
        b = resolve_ref(storage, _ref_from_url(r.get("url")))
        if b:
            imgs.append(b)
    heads = []
    for c in store.find("cards", deck_id=d["id"]):
        if c.get("status") == "archived" or c.get("synthetic"):
            continue
        v = store.get("versions", c.get("current_version_id") or "")
        if v and v.get("image_url"):
            heads.append((c.get("status") == "landed", v["image_url"]))
    landed = [u for ok, u in heads if ok]
    for u in (landed or [u for _, u in heads])[:12]:
        b = resolve_ref(storage, _ref_from_url(u))
        if b:
            imgs.append(b)
    if not imgs:
        return None
    import numpy as np

    vecs = [image_embed(b) for b in imgs]
    c = np.mean(vecs, axis=0)
    n = float(np.linalg.norm(c))
    centroid = [float(x) for x in (c / n if n > 0 else c)]
    fresh = store.get("decks", d["id"]) or d
    fresh.setdefault("style_guide", {})["style_centroid_embedding"] = centroid
    fresh["style_guide"]["style_centroid_backend"] = image_embed_backend()
    fresh["updated_at"] = now_iso()
    store.put("decks", fresh)
    return centroid


# ----------------------------------------------------------------------------- reinterpret (§5.6)
def start_reinterpret(store, jobs, storage, deck: Any, user: Any, body: dict) -> dict:
    d = _deck_dict(deck)
    uid = _uid(user)
    slug = body.get("base_deck_slug") or ""
    base = decks_svc.base_deck(store, slug) or decks_svc.base_deck(store, (d.get("origin") or {}).get("base_deck_id"))
    if base is None:
        raise CardError(404, "not_found", "no such base deck")
    st = decks_svc.structure(d.get("structure_template_id") or "free")
    base_cards = {c["position_key"]: c for c in store.find("base_cards", base_deck_id=base["id"])}
    wanted = body.get("positions")
    group = body.get("group")
    if wanted:
        keys = [k for k in wanted if k in base_cards]
    elif group:
        keys = [p.key for p in st.positions if p.group == group and p.key in base_cards]
    else:
        keys = [p.key for p in st.positions if p.key in base_cards] if st.positions else list(base_cards)
    taken = {c["position_key"] for c in store.find("cards", deck_id=d["id"]) if c.get("status") != "archived"}
    keys = [k for k in keys if k not in taken]
    if not keys:
        raise CardError(422, "validation", "no free positions match that selection")
    check_quota(store, deck, len(keys))
    check_rate(store, uid)
    payload = {"deck_id": d["id"], "user_id": uid, "base_deck_id": base["id"], "base_slug": base.get("slug"), "positions": keys,
               "assign_makers": body.get("assign_makers") or {}, "n": max(1, min(2, int(body.get("n") or 1)))}
    job = jobs.enqueue("reinterpret_batch", payload, created_by=uid, deck_id=d["id"])
    activity.log(store, d["id"], uid, "reinterpret.started", {"job_id": job["id"], "positions": len(keys), "base_deck_id": base["id"]})
    return {"job": J.public_job(job), "positions": keys}


@J.register("reinterpret_batch")
def _job_reinterpret(ctx: J.JobContext):
    store, storage = ctx.store, ctx.services.get("storage")
    imaging = ctx.services.get("imaging")
    if imaging is None or storage is None:
        raise J.NonRetryable("imaging pipeline or storage not available")
    p = ctx.payload
    deck_d = store.get("decks", p["deck_id"])
    base = store.get("base_decks", p["base_deck_id"])
    if deck_d is None or base is None:
        raise J.NonRetryable("deck or base deck vanished")
    st = decks_svc.structure(deck_d.get("structure_template_id") or "free")
    titles = {q.key: q.title for q in st.positions}
    symbols = active_symbols(store, deck_d["id"])
    by_key = {s.get("key"): s for s in symbols.values()}
    mapping = decks_svc.symbols_by_position(store, base)
    base_cards = {c["position_key"]: c for c in store.find("base_cards", base_deck_id=base["id"])}
    style_refs = _style_ref_refs(store, deck_d)
    done, failed = [], []
    for i, key in enumerate(p["positions"]):
        ctx.progress(i / max(1, len(p["positions"])), f"{key} ({i + 1}/{len(p['positions'])})")
        bc = base_cards.get(key)
        if bc is None:
            failed.append({"position_key": key, "error": "no base card"})
            continue
        if any(c.get("status") != "archived" for c in store.find("cards", deck_id=deck_d["id"], position_key=key)):
            continue
        maker = (p.get("assign_makers") or {}).get(key) or p.get("user_id")
        declared_syms = [by_key[bs["key"]] for bs in mapping.get(key, []) if bs.get("key") in by_key]
        card = {"id": new_id("c_"), "deck_id": deck_d["id"], "position_key": key, "title": titles.get(key) or bc.get("title"), "maker_id": maker,
                "intent": None, "approved_editors": "*", "edit_requests": [], "status": "draft", "current_version_id": None, "branches": [],
                "tags": ["reinterpreted"], "share_token": secrets.token_urlsafe(8), "encoder_ids": [maker], "pending_version_id": None,
                "synthetic": False, "created_at": now_iso(), "updated_at": now_iso()}
        store.put("cards", card)
        how = {"kind": "generation", "mode": "reinterpret", "reference_image_url": bc.get("image_url"), "prompt_user": f"reinterpret {bc.get('title', key)}",
               "prompt_full": "", "provider": "", "model": "", "seed": None, "candidates": [], "chosen_index": None, "base_card_id": bc["id"]}
        version = _new_version_doc(deck_d["id"], card, "main", None, 0, how, maker)
        version["symbols_declared"] = [{"symbol_id": s["id"], "placement": s.get("placement") if s.get("placement") != "any" else None} for s in declared_syms]
        store.put("versions", version)
        ref = resolve_ref(storage, _ref_from_url(bc.get("image_url")))
        im = {"provider": (deck_d.get("settings") or {}).get("provider") or None, "style_guide": _style_guide_dict(deck_d), "position_title": card["title"],
              "symbols": [_hydrate_symbol(storage, symbol_payload(s)) for s in declared_syms], "prompt_user": how["prompt_user"],
              "aspect": (deck_d.get("style_guide") or {}).get("aspect") or "2.75x4.75", "n": int(p.get("n", 1)),
              "style_refs": ([ref] if ref else []) + [b for b in (resolve_ref(storage, r) for r in style_refs) if b][:2],
              "style_centroid": (deck_d.get("style_guide") or {}).get("style_centroid_embedding"), "registry": registry_for(symbols),
              "storage_prefix": f"decks/{deck_d['id']}/cards/{card['id']}/gen_{version['id']}"}
        result = None
        for attempt in range(2):
            try:
                result = imaging.run_generate(im, {"storage_put": storage.put})
                break
            except Exception as e:  # retry individually
                result = {"error": f"{type(e).__name__}: {e}"}
        if not result or result.get("blocked") or not result.get("candidates"):
            version["status"] = "blocked"
            version["checks"]["safety"] = "blocked"
            version["checks"]["safety_reason"] = (result or {}).get("reason") or (result or {}).get("error") or "no candidates"
            store.put("versions", version)
            failed.append({"position_key": key, "card_id": card["id"], "error": version["checks"]["safety_reason"]})
            continue
        how.update({"prompt_full": result.get("prompt_full", ""), "provider": result.get("provider", ""), "model": result.get("model", ""),
                    "seed": result.get("seed"), "candidates": result["candidates"]})
        best = max(result["candidates"], key=lambda c: (c.get("style_score") or 0.0))
        _version_from_candidate(storage, version, best, int(best.get("index", 0)))
        _attach_version(store, storage, deck_d, card, version, maker)
        done.append({"position_key": key, "card_id": card["id"], "version_id": version["id"]})
    ctx.progress(1.0, "done")
    activity.log(store, deck_d["id"], p.get("user_id"), "reinterpret.finished", {"done": len(done), "failed": len(failed)})
    if p.get("user_id"):
        notifications.notify(store, p["user_id"], "reinterpret.done", f"reinterpretation finished: {len(done)} cards, {len(failed)} failed", deck_d["id"])
    return {"done": done, "failed": failed}


# ----------------------------------------------------------------------------- views
def card_view(store, storage, deck: Any, card: dict, user: Any) -> dict:
    d = _deck_dict(deck)
    deck_m = deck if hasattr(deck, "to_doc") else Deck(**deck)
    uid = _uid(user)
    role = role_in_deck(store, deck_m, user)
    curator = at_least(role, "curator")
    encoder = bool(uid) and (card.get("maker_id") == uid or uid in (card.get("encoder_ids") or []))
    public = card.get("status") in ("landed", "closed")
    out = {k: v for k, v in card.items() if k not in ("intent",)}
    if encoder or curator or public:
        out["intent"] = card.get("intent")
    cur = store.get("versions", card.get("current_version_id") or "") if card.get("current_version_id") else None
    if cur:
        out["current_version"] = {k: v for k, v in cur.items() if k != "how"} | {"how": {k: v for k, v in (cur.get("how") or {}).items() if k != "candidates"}}
    else:
        out["current_version"] = None
    out["versions"] = list_versions(store, card)["versions"]
    pending = store.get("versions", card.get("pending_version_id") or "") if card.get("pending_version_id") else None
    if pending and pending.get("status") in ("candidates", "blocked") and (pending.get("created_by") == uid or curator):
        out["pending_version"] = {**{k: v for k, v in pending.items() if k != "how"},
                                  "how": {**{k: v for k, v in pending["how"].items() if k != "candidates"}, "candidates": _public_candidates(storage, pending["how"].get("candidates") or [])}}
    else:
        out["pending_version"] = None
    from service import readings as _rd

    thr = _rd.effective_threshold(store, d, card)
    n_h = human_readings(store, cur["id"]) if cur else 0
    can_edit = bool(uid) and card.get("status") == "open" and is_approved_editor(store, _card_model(card), deck_m, user)
    can_branch_edit = bool(uid) and card.get("status") == "reading" and curator and bool(d.get("settings", {}).get("allow_branches", True)) and cur is not None
    out["can"] = {"edit": can_edit or can_branch_edit, "request_edit": bool(uid) and at_least(role, "member") and not can_edit and card.get("maker_id") != uid and card.get("status") not in ("archived",),
                  "archive": bool(uid) and (card.get("maker_id") == uid or curator) and card.get("status") != "archived",
                  "generate": bool(uid) and (card.get("maker_id") == uid or curator) and card.get("status") != "archived",
                  "set_intent": bool(uid) and card.get("maker_id") == uid, "read": bool(uid) and card.get("maker_id") != uid and card.get("status") in ("reading", "open"),
                  "branch": curator and bool(d.get("settings", {}).get("allow_branches", True)),
                  "open_for_edits": bool(uid) and card.get("status") == "reading" and n_h >= 1 and (card.get("maker_id") == uid or curator)}
    out["role"] = role
    n_all = len(store.find("readings", version_id=cur["id"])) if cur else 0
    out["readings"] = {"n_human": n_h, "n_synthetic": max(0, n_all - n_h), "threshold": thr, "ready": n_h >= thr}
    try:
        out["verdict"] = measure.verdict(store, d["id"], cur) if cur else None
        out["fidelity"] = measure.version_fidelity(card, measure.version_readings(store, cur["id"])) if cur else None
    except Exception as e:  # never break the studio on measurement
        out["verdict"], out["fidelity"] = None, None
        print(f"[cards] verdict skipped: {type(e).__name__}: {e}")
    out["is_encoder"] = encoder
    return out


def list_cards(store, deck: Any, user: Any, filters: dict) -> list[dict]:
    d = _deck_dict(deck)
    uid = _uid(user)
    thr = int(d.get("settings", {}).get("ready_threshold", 3))
    sthr = float(d.get("settings", {}).get("style_threshold", 0.70))
    cards = [c for c in store.find("cards", deck_id=d["id"]) if c.get("status") != "archived" or filters.get("status") == "archived"]
    if filters.get("status"):
        cards = [c for c in cards if c.get("status") == filters["status"]]
    if filters.get("mine"):
        cards = [c for c in cards if c.get("maker_id") == uid or uid in (c.get("encoder_ids") or [])]
    contested_ids: set[str] | None = None
    if filters.get("contested"):
        from service import coherence

        work = coherence.dashboard(store, d).get("semantic", {}).get("symbols", [])
        contested_ids = {c["card_id"] for r in work if r.get("coherence") == "contested" for c in r.get("cards", [])}
    out = []
    for c in cards:
        v = store.get("versions", c.get("current_version_id") or "") if c.get("current_version_id") else None
        n_h = human_readings(store, v["id"]) if v else 0
        style = (v or {}).get("checks", {}).get("style_score")
        tile = {"id": c["id"], "position_key": c.get("position_key"), "title": c.get("title"), "status": c.get("status"), "maker_id": c.get("maker_id"),
                "thumb_url": (v or {}).get("thumb_url") or (v or {}).get("image_url"), "image_url": (v or {}).get("image_url"), "v": (v or {}).get("v"),
                "n_readings": n_h, "needs_readings": c.get("status") in ("reading", "draft") and n_h < thr, "style_score": style,
                "off_style": style is not None and style < sthr, "n_editors": max(0, len(c.get("encoder_ids") or []) - 1),
                "n_branches": len(c.get("branches") or []), "has_intent": bool((c.get("intent") or {}).get("statement")),
                "fidelity": None, "verdict": None, "synthetic": bool(c.get("synthetic")), "contested": bool(contested_ids and c["id"] in contested_ids),
                "pending": bool(c.get("pending_version_id")), "updated_at": c.get("updated_at")}
        if v and c.get("status") in ("reading", "open", "landed", "closed"):
            try:
                rs = measure.version_readings(store, v["id"])
                tile["fidelity"] = measure.version_fidelity(c, rs) if rs else None
                tile["verdict"] = measure.verdict(store, d["id"], v)["verdict"]
            except Exception:
                pass
        if filters.get("needs_readings") and not tile["needs_readings"]:
            continue
        if filters.get("off_style") and not tile["off_style"]:
            continue
        if filters.get("contested") and not tile["contested"]:
            continue
        if filters.get("open_for_edit") and c.get("status") != "open":
            continue
        out.append(tile)
    out.sort(key=lambda t: (t["position_key"] or ""))
    return out

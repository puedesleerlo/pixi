"""Admin console (spec §4.8, §11 Admin) + reports (moderation queue)."""
from __future__ import annotations

import os
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_admin, require_user
from models import User
from routers.deps import jobs, store
from pixie import relay as R

router = APIRouter(prefix="/api", tags=["admin"])


class ReportBody(BaseModel):
    kind: str  # card | symbol | deck
    ref_id: str
    reason: str = Field(min_length=1, max_length=280)


class QuotaBody(BaseModel):
    deck_id: str
    generation_quota_month: int = Field(ge=0)


def _provider_status() -> dict:
    from pixie.embed import backend_name as embed_backend
    from pixie.naming import naming_backend

    out = {"embed_text": embed_backend(), "naming": naming_backend(), "store": store().kind}
    try:
        from pixie.imaging.providers.base import get_provider
        from pixie.imaging.fidelity import image_embed_backend

        p = get_provider()
        out["image_provider"] = getattr(p, "name", type(p).__name__)
        out["image_model"] = getattr(p, "model", None)
        out["image_embed"] = image_embed_backend()
    except Exception as e:
        out["image_provider_error"] = f"{type(e).__name__}: {e}"
    out["vision_tagger"] = "gemini" if os.environ.get("GEMINI_API_KEY") and os.environ.get("PIXIE_DETECT") != "fallback" else "declared_only"
    out["keys"] = {k: bool(os.environ.get(k)) for k in ("GEMINI_API_KEY", "BFL_API_KEY", "OPENAI_API_KEY", "K2_ENDPOINT", "MONGODB_URI", "AUTH0_DOMAIN", "S3_BUCKET", "RESEND_API_KEY")}
    return out


@router.post("/reports")
def report(body: ReportBody, user: User = Depends(require_user)):
    if body.kind not in ("card", "symbol", "deck"):
        raise HTTPException(422, {"code": "validation", "detail": "kind must be card, symbol or deck"})
    doc = {"id": R.new_id("rp_"), "kind": body.kind, "ref_id": body.ref_id, "reason": body.reason, "reporter_id": user.id, "status": "open",
           "created_at": R.iso(R.utcnow()), "updated_at": R.iso(R.utcnow())}
    store().put("reports", doc)
    return doc


@router.get("/admin/providers/health")
def providers_health(admin: User = Depends(require_admin)):
    t = time.time()
    return {**_provider_status(), "checked_in_ms": int((time.time() - t) * 1000)}


@router.get("/admin/moderation")
def moderation(status: str = "open", admin: User = Depends(require_admin)):
    return store().find("reports", status=status) if status != "all" else store().all("reports")


@router.patch("/admin/moderation/{rid}")
def moderate(rid: str, action: str, admin: User = Depends(require_admin)):
    rp = store().get("reports", rid)
    if rp is None:
        raise HTTPException(404, {"code": "not_found", "detail": "no such report"})
    if action not in ("dismiss", "archive_target"):
        raise HTTPException(422, {"code": "validation", "detail": "action must be dismiss or archive_target"})
    if action == "archive_target":
        coll = {"card": "cards", "symbol": "symbols", "deck": "decks"}[rp["kind"]]
        target = store().get(coll, rp["ref_id"])
        if target is not None:
            target["status"] = "archived" if rp["kind"] != "deck" else target.get("status")
            if rp["kind"] == "deck":
                target["visibility"] = "private"
            store().put(coll, target)
    rp["status"] = "closed"
    rp["decided_by"] = admin.id
    rp["action"] = action
    rp["updated_at"] = R.iso(R.utcnow())
    store().put("reports", rp)
    return rp


@router.patch("/admin/quotas")
def quotas(body: QuotaBody, admin: User = Depends(require_admin)):
    d = store().get("decks", body.deck_id)
    if d is None:
        raise HTTPException(404, {"code": "not_found", "detail": "no such deck"})
    d.setdefault("settings", {})["generation_quota_month"] = body.generation_quota_month
    store().put("decks", d)
    return d["settings"]


@router.get("/admin/metrics")
def metrics(admin: User = Depends(require_admin)):
    s = store()
    jobs_all = s.all("jobs")
    by_status: dict[str, int] = {}
    for j in jobs_all:
        by_status[j.get("status", "?")] = by_status.get(j.get("status", "?"), 0) + 1
    versions = s.all("versions")
    generated = [v for v in versions if (v.get("how") or {}).get("provider") not in (None, "seed", "fork", "base_deck")]
    return {"users": s.count("users"), "decks": s.count("decks"), "cards": s.count("cards"), "versions": len(versions), "readings": s.count("readings"),
            "sessions": s.count("sessions"), "jobs": by_status, "generated_versions": len(generated),
            "estimated_cost_usd": round(sum(float((v.get("how") or {}).get("cost_estimate") or 0.0) for v in generated), 2),
            "reports_open": s.count("reports", status="open")}


@router.get("/admin/feature-flags")
def feature_flags(admin: User = Depends(require_admin)):
    return {k: os.environ.get(k) for k in ("PIXIE_IMAGE_PROVIDER", "PIXIE_DETECT", "PIXIE_IMAGE_EMBED", "PIXIE_WORKER", "PIXIE_EMBED")}

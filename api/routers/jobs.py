from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from auth import require_user
from jobs import job_event_stream, public_job
from models import User
from routers.deps import jobs, store

router = APIRouter(prefix="/api", tags=["jobs"])


def _visible(job: dict, user: User) -> bool:
    from auth import is_admin
    if is_admin(user) or job.get("created_by") == user.id:
        return True
    if job.get("deck_id"):
        from service.permissions import can_view
        from service import decks as decks_svc
        try:
            return can_view(store(), decks_svc.get_deck(store(), job["deck_id"]), user)
        except Exception:
            return False
    return False


@router.get("/jobs/{jid}")
def get_job(jid: str, user: User = Depends(require_user)):
    job = jobs().get(jid)
    if job is None or not _visible(job, user):
        raise HTTPException(404, {"code": "not_found", "detail": "no such job"})
    return public_job(job)


@router.get("/jobs/{jid}/events")
def job_events(jid: str, user: User = Depends(require_user)):
    job = jobs().get(jid)
    if job is None or not _visible(job, user):
        raise HTTPException(404, {"code": "not_found", "detail": "no such job"})
    return StreamingResponse(job_event_stream(store(), jid), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/jobs/test", status_code=201)
def test_job(body: dict | None = None, user: User = Depends(require_user)):
    """A demo job for the foundations slice (counts with progress)."""
    return public_job(jobs().enqueue("test", body or {"n": 3}, created_by=user.id))

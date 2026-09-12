from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth import require_user
from models import NotificationPatch, User
from routers.deps import store
from service import notifications as notif

router = APIRouter(prefix="/api", tags=["notifications"])


@router.get("/notifications")
def list_notifications(unread: bool = False, user: User = Depends(require_user)):
    rows = notif.list_for(store(), user.id, unread_only=unread)
    return {"unread": sum(1 for r in rows if not r.get("read_at")), "items": rows}


@router.patch("/notifications/{nid}")
def patch_notification(nid: str, body: NotificationPatch, user: User = Depends(require_user)):
    n = notif.mark(store(), nid, user.id, body.read)
    if n is None:
        raise HTTPException(404, {"code": "not_found", "detail": "no such notification"})
    return n


@router.post("/notifications/read-all")
def read_all(user: User = Depends(require_user)):
    n = 0
    for r in notif.list_for(store(), user.id, unread_only=True):
        notif.mark(store(), r["id"], user.id, True)
        n += 1
    return {"marked": n}

from __future__ import annotations

from auth import new_id
from models import Notification, now_iso


def notify(store, user_id: str, kind: str, text: str, deck_id: str | None = None, card_id: str | None = None) -> dict:
    n = Notification(id=new_id("n_"), user_id=user_id, kind=kind, text=text, deck_id=deck_id, card_id=card_id).to_doc()
    store.put("notifications", n)
    return n


def list_for(store, user_id: str, unread_only: bool = False, limit: int = 100) -> list[dict]:
    rows = store.find("notifications", user_id=user_id)
    if unread_only:
        rows = [r for r in rows if not r.get("read_at")]
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows[:limit]


def mark(store, nid: str, user_id: str, read: bool = True) -> dict | None:
    n = store.get("notifications", nid)
    if n is None or n.get("user_id") != user_id:
        return None
    n["read_at"] = now_iso() if read else None
    n["updated_at"] = now_iso()
    store.put("notifications", n)
    return n

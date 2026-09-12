from __future__ import annotations

from auth import new_id
from models import Activity


def log(store, deck_id: str, actor_id: str | None, kind: str, refs: dict | None = None) -> dict:
    a = Activity(id=new_id("a_"), deck_id=deck_id, actor_id=actor_id, kind=kind, refs=refs or {}).to_doc()
    store.put("activities", a)
    return a


def feed(store, deck_id: str, limit: int = 50) -> list[dict]:
    rows = store.find("activities", deck_id=deck_id)
    rows.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    return rows[:limit]


def feed_for_user(store, user_id: str, limit: int = 50) -> list[dict]:
    deck_ids = {m["deck_id"] for m in store.find("memberships", user_id=user_id)} | {d["id"] for d in store.find("decks", owner_id=user_id)}
    rows = [a for a in store.all("activities") if a.get("deck_id") in deck_ids]
    rows.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    return rows[:limit]

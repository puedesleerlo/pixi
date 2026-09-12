"""Storage: MongoDB Atlas when MONGODB_URI is set, otherwise an in-memory store
with a JSON snapshot on disk so a restart at 3 am loses nothing.

Both back ends expose the same tiny API. Documents are plain dicts with an "id".
Derived tables (grammar, verdict, transmission events) are NOT stored; they are
recomputed on read (milliseconds at this size).
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Iterable

SNAPSHOT_COLLECTIONS = (
    # v4
    "libraries", "elements", "rooms", "config", "pca", "meta",
    # v5 (spec §3)
    "users", "base_decks", "base_cards", "base_symbols", "decks", "memberships", "invitations",
    "structure_templates", "symbols", "symbol_proposals", "cards", "versions", "readings", "sessions",
    "rounds", "fork_snapshots", "upstream_proposals", "jobs", "notifications", "activities", "magic_tokens",
)


def _match(doc: dict, filters: dict) -> bool:
    for k, v in filters.items():
        if doc.get(k) != v:
            return False
    return True


class MemoryStore:
    kind = "memory"

    def __init__(self, snapshot_path: str | None = None):
        self._c: dict[str, dict[str, dict]] = {}
        self._lock = threading.RLock()
        self._snapshot_path = snapshot_path
        self._dirty = False
        self._last_flush = 0.0
        if snapshot_path and os.path.exists(snapshot_path):
            try:
                with open(snapshot_path) as f:
                    raw = json.load(f)
                for coll, docs in raw.items():
                    self._c[coll] = {d["id"]: d for d in docs}
            except Exception as e:  # corrupt snapshot: start clean, keep the file for forensics
                print(f"[store] snapshot unreadable ({e}); starting empty")

    # -- generic API ---------------------------------------------------------
    def get(self, coll: str, id: str) -> dict | None:
        with self._lock:
            d = self._c.get(coll, {}).get(id)
            return json.loads(json.dumps(d)) if d is not None else None

    def put(self, coll: str, doc: dict) -> dict:
        assert "id" in doc, "documents need an id"
        with self._lock:
            self._c.setdefault(coll, {})[doc["id"]] = json.loads(json.dumps(doc))
            self._mark(coll)
        return doc

    def put_many(self, coll: str, docs: Iterable[dict]) -> int:
        n = 0
        with self._lock:
            bucket = self._c.setdefault(coll, {})
            for d in docs:
                bucket[d["id"]] = json.loads(json.dumps(d))
                n += 1
            self._mark(coll)
        return n

    def find(self, coll: str, **filters: Any) -> list[dict]:
        with self._lock:
            docs = [d for d in self._c.get(coll, {}).values() if _match(d, filters)]
            return json.loads(json.dumps(docs))

    def all(self, coll: str) -> list[dict]:
        return self.find(coll)

    def count(self, coll: str, **filters: Any) -> int:
        with self._lock:
            return sum(1 for d in self._c.get(coll, {}).values() if _match(d, filters))

    def delete(self, coll: str, id: str) -> None:
        with self._lock:
            self._c.get(coll, {}).pop(id, None)
            self._mark(coll)

    def clear(self, coll: str) -> None:
        with self._lock:
            self._c[coll] = {}
            self._mark(coll)

    # -- snapshot --------------------------------------------------------------
    def _mark(self, coll: str) -> None:
        if coll in SNAPSHOT_COLLECTIONS and self._snapshot_path:
            self._dirty = True
            # flush at most every 0.5 s; readings arrive in bursts during a round
            if time.time() - self._last_flush > 0.5:
                self.flush()

    def flush(self) -> None:
        if not (self._snapshot_path and self._dirty):
            return
        with self._lock:
            raw = {c: list(self._c.get(c, {}).values()) for c in SNAPSHOT_COLLECTIONS}
            tmp = self._snapshot_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(raw, f)
            os.replace(tmp, self._snapshot_path)
            self._dirty = False
            self._last_flush = time.time()


class MongoStore:
    kind = "mongo"

    def __init__(self, uri: str, db_name: str = "pixie"):
        from pymongo import MongoClient  # imported lazily so memory mode has no dependency

        self._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self._db = self._client[db_name]
        self._db.command("ping")

    @staticmethod
    def _out(d: dict | None) -> dict | None:
        if d is None:
            return None
        d = dict(d)
        d.pop("_id", None)
        return d

    def get(self, coll: str, id: str) -> dict | None:
        return self._out(self._db[coll].find_one({"_id": id}))

    def put(self, coll: str, doc: dict) -> dict:
        body = dict(doc)
        body["_id"] = doc["id"]
        self._db[coll].replace_one({"_id": doc["id"]}, body, upsert=True)
        return doc

    def put_many(self, coll: str, docs: Iterable[dict]) -> int:
        from pymongo import ReplaceOne

        ops = [ReplaceOne({"_id": d["id"]}, {**d, "_id": d["id"]}, upsert=True) for d in docs]
        if not ops:
            return 0
        self._db[coll].bulk_write(ops, ordered=False)
        return len(ops)

    def find(self, coll: str, **filters: Any) -> list[dict]:
        return [self._out(d) for d in self._db[coll].find(filters)]

    def all(self, coll: str) -> list[dict]:
        return self.find(coll)

    def count(self, coll: str, **filters: Any) -> int:
        return self._db[coll].count_documents(filters)

    def delete(self, coll: str, id: str) -> None:
        self._db[coll].delete_one({"_id": id})

    def clear(self, coll: str) -> None:
        self._db[coll].delete_many({})

    def flush(self) -> None:
        pass


def open_store(snapshot_path: str | None = None):
    """MONGODB_URI set and reachable → Mongo; anything else → memory + snapshot.
    Never let the database block the demo."""
    uri = os.environ.get("MONGODB_URI")
    if uri:
        try:
            s = MongoStore(uri, os.environ.get("MONGODB_DB", "pixie"))
            print("[store] MongoDB Atlas connected")
            return s
        except Exception as e:
            print(f"[store] Mongo unavailable ({type(e).__name__}: {e}); falling back to memory")
    return MemoryStore(snapshot_path)

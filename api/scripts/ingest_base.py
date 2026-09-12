"""Ingest a base deck from its manifest into the store.

  python api/scripts/ingest_base.py --slug smith1909            # keep Commons URLs
  python api/scripts/ingest_base.py --slug smith1909 --download # normalise + store images via storage.py (if present)
  python api/scripts/ingest_base.py --all
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.dirname(HERE)
sys.path.insert(0, API)

from pixie.store import open_store  # noqa: E402
from service import base_decks as svc  # noqa: E402


class _Ctx:
    def progress(self, p: float, note: str = "") -> None:
        print(f"\r  {p * 100:5.1f}%  {note:40s}", end="", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--snapshot", default=os.environ.get("PIXIE_SNAPSHOT", os.path.join(API, ".pixie_state.json")))
    a = ap.parse_args()
    store = open_store(a.snapshot)
    storage = None
    if a.download:
        try:
            from storage import LocalStorage  # B1's module, optional

            storage = LocalStorage()
        except Exception as e:
            print(f"storage.py unavailable ({e}); keeping Commons URLs")
    slugs = list(svc.load_manifests()) if a.all else [a.slug]
    for slug in slugs:
        if not slug:
            ap.error("--slug or --all")
        res = svc.ingest(store, storage, slug, job_ctx=_Ctx() if a.download else None)
        print(f"\n{res}")
    store.flush()


if __name__ == "__main__":
    main()

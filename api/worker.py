"""External job worker: `PIXIE_WORKER=external uvicorn main:app` + `python worker.py` in another process.
Shares the store (Mongo, or the same snapshot file — memory mode is single-process, so use Mongo here)."""
from __future__ import annotations

import os
import time

os.environ.setdefault("PIXIE_WORKER", "external")

from jobs import JobRunner  # noqa: E402
from main import SNAPSHOT, build_services  # noqa: E402
from pixie.store import open_store  # noqa: E402
from storage import open_storage  # noqa: E402

if __name__ == "__main__":
    store = open_store(SNAPSHOT)
    services = build_services()
    services.update({"store": store, "storage": open_storage()})
    runner = JobRunner(store, mode="external", services=services)
    print("[worker] running; polling for queued jobs")
    while True:
        n = runner.run_pending()
        time.sleep(0.5 if n else 2.0)

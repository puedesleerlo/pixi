"""Jobs (spec §3.11, contract §5): store-backed job docs, a handler registry, and a runner.

PIXIE_WORKER = thread (default: in-process pool) | inline (run synchronously on enqueue; tests) |
external (only enqueue; `python worker.py` executes). Retries 3 with backoff. Idempotency key
returns the existing job. SSE helpers stream job.progress / job.done / job.failed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from models import Job, now_iso

HANDLERS: dict[str, Callable[["JobContext"], Any]] = {}
MAX_ATTEMPTS = 3
BACKOFF = (0.5, 2.0, 5.0)


def register(kind: str):
    def deco(fn: Callable[["JobContext"], Any]):
        HANDLERS[kind] = fn
        return fn
    return deco


def idempotency_key(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:24]


class JobContext:
    def __init__(self, runner: "JobRunner", job: dict):
        self.runner = runner
        self.job = job
        self.store = runner.store
        self.services = runner.services  # engine, storage, … (dict filled by main)

    @property
    def payload(self) -> dict:
        return self.job.get("payload") or {}

    def progress(self, p: float, note: str | None = None) -> None:
        self.job["progress"] = float(max(0.0, min(1.0, p)))
        if note:
            self.job["note"] = note
        self.job["updated_at"] = now_iso()
        self.store.put("jobs", self.job)


class JobRunner:
    def __init__(self, store, mode: str | None = None, services: dict | None = None, max_workers: int = 2):
        self.store = store
        self.mode = mode or os.environ.get("PIXIE_WORKER", "thread")
        self.services = services or {}
        self.pool = ThreadPoolExecutor(max_workers=max_workers) if self.mode == "thread" else None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ api
    def enqueue(self, kind: str, payload: dict, created_by: str | None = None, deck_id: str | None = None,
                idempotency_key: str | None = None) -> dict:
        if idempotency_key:
            existing = self.store.find("jobs", idempotency_key=idempotency_key)
            if existing:
                return existing[0]
        from auth import new_id

        job = Job(id=new_id("j_"), kind=kind, deck_id=deck_id, payload=payload, created_by=created_by,
                  idempotency_key=idempotency_key).to_doc()
        self.store.put("jobs", job)
        if self.mode == "inline":
            self.run(job["id"])
            return self.store.get("jobs", job["id"])
        if self.mode == "thread":
            self.pool.submit(self._run_with_retries, job["id"])
        return job

    def get(self, job_id: str) -> dict | None:
        return self.store.get("jobs", job_id)

    # ------------------------------------------------------------------ execution
    def run(self, job_id: str) -> dict:
        """Run once with retries, synchronously (used by inline mode and by worker.py)."""
        self._run_with_retries(job_id)
        return self.store.get("jobs", job_id)

    def _run_with_retries(self, job_id: str) -> None:
        for attempt in range(MAX_ATTEMPTS):
            ok = self._run_once(job_id)
            if ok:
                return
            job = self.store.get("jobs", job_id)
            if job and job.get("status") == "failed" and job.get("attempts", 0) >= MAX_ATTEMPTS:
                return
            time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)] if self.mode != "inline" else 0)

    def _run_once(self, job_id: str) -> bool:
        job = self.store.get("jobs", job_id)
        if job is None or job.get("status") == "done":
            return True
        handler = HANDLERS.get(job["kind"])
        job["status"] = "running"
        job["attempts"] = int(job.get("attempts", 0)) + 1
        job["started_at"] = job.get("started_at") or now_iso()
        job["updated_at"] = now_iso()
        self.store.put("jobs", job)
        ctx = JobContext(self, job)
        try:
            if handler is None:
                raise RuntimeError(f"no handler for job kind {job['kind']!r}")
            result = handler(ctx)
            job = ctx.job
            job.update({"status": "done", "progress": 1.0, "result": result, "error": None, "finished_at": now_iso(), "updated_at": now_iso()})
            self.store.put("jobs", job)
            return True
        except Exception as e:  # noqa: BLE001
            job = ctx.job
            job.pop("result", None)  # a result that could not be stored must not poison the failure record
            err = f"{type(e).__name__}: {e}"
            print(f"[jobs] {job.get('kind')} {job_id} attempt {job.get('attempts')}: {err}")
            final = job["attempts"] >= MAX_ATTEMPTS or isinstance(e, NonRetryable)
            job.update({"status": "failed" if final else "queued", "error": err, "updated_at": now_iso(),
                        "finished_at": now_iso() if final else None, "trace": traceback.format_exc()[-2000:]})
            if isinstance(e, NonRetryable):
                job["attempts"] = MAX_ATTEMPTS
            try:
                self.store.put("jobs", job)
            except Exception as e2:  # last resort: never leave the job 'running'
                print(f"[jobs] could not store the failure record for {job_id}: {e2}")
                self.store.put("jobs", {k: v for k, v in job.items() if k in ("id", "kind", "deck_id", "created_by", "created_at", "attempts")} | {"status": "failed", "error": err, "updated_at": now_iso(), "finished_at": now_iso()})
            return False

    def recover_stale(self) -> int:
        """At boot: a job left 'running' by a previous process can never finish; re-queue it (or fail it)."""
        n = 0
        for job in self.store.find("jobs", status="running"):
            job["status"] = "queued" if int(job.get("attempts", 0)) < MAX_ATTEMPTS else "failed"
            job["error"] = "interrupted: the server restarted while this job was running"
            job["updated_at"] = now_iso()
            self.store.put("jobs", job)
            n += 1
            if job["status"] == "queued" and self.mode == "thread":
                self.pool.submit(self._run_with_retries, job["id"])
        return n

    def run_pending(self, limit: int = 10) -> int:
        """External worker loop step: run queued jobs."""
        n = 0
        for job in sorted(self.store.find("jobs", status="queued"), key=lambda j: j.get("created_at") or "")[:limit]:
            self._run_with_retries(job["id"])
            n += 1
        return n


class NonRetryable(Exception):
    """Raise from a handler when retrying cannot help (validation, quota, safety block)."""


# ----------------------------------------------------------------------------- SSE
def sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def public_job(job: dict) -> dict:
    return {k: v for k, v in job.items() if k not in ("trace",)}


async def job_event_stream(store, job_id: str, poll: float = 0.5, heartbeat: float = 15.0, timeout: float = 600.0):
    """Yields SSE frames until the job reaches done/failed (or the timeout)."""
    last = None
    t0 = time.time()
    last_beat = t0
    while time.time() - t0 < timeout:
        job = store.get("jobs", job_id)
        if job is None:
            yield sse("job.failed", {"id": job_id, "error": "not found"})
            return
        snap = (job.get("status"), round(float(job.get("progress", 0)), 3), job.get("note"))
        if snap != last:
            last = snap
            if job["status"] == "done":
                yield sse("job.done", public_job(job))
                return
            if job["status"] == "failed":
                yield sse("job.failed", public_job(job))
                return
            yield sse("job.progress", {"id": job_id, "status": job["status"], "progress": job.get("progress", 0), "note": job.get("note")})
            last_beat = time.time()
        elif time.time() - last_beat >= heartbeat:
            yield ": ping\n\n"
            last_beat = time.time()
        await asyncio.sleep(poll)
    yield sse("job.failed", {"id": job_id, "error": "stream timeout"})


@register("test")
def _test_job(ctx: JobContext):
    """A demo job: counts to n with progress. `fail_times` makes it raise on the first attempts."""
    n = int(ctx.payload.get("n", 3))
    fail_times = int(ctx.payload.get("fail_times", 0))
    if ctx.job.get("attempts", 1) <= fail_times:
        raise RuntimeError("simulated failure")
    for i in range(n):
        ctx.progress((i + 1) / n, f"step {i + 1}/{n}")
        if ctx.payload.get("sleep"):
            time.sleep(float(ctx.payload["sleep"]))
    return {"counted": n}

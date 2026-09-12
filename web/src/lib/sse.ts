"use client";
import { v5 } from "./api";
import type { Job } from "./types";

/**
 * Subscribe to a job over SSE (`/api/jobs/{jid}/events`), falling back to polling `GET /api/jobs/{jid}`
 * every 1.5 s when EventSource is unavailable or errors. Returns an unsubscribe function.
 */
export function subscribeJob(jid: string, onJob: (job: Job) => void, onError?: (e: unknown) => void): () => void {
  let stopped = false;
  let es: EventSource | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;

  const poll = () => {
    if (timer) return;
    timer = setInterval(async () => {
      if (stopped) return;
      try {
        const j = await v5.jobs.get(jid);
        onJob(j);
        if (j.status === "done" || j.status === "failed") stop();
      } catch (e) {
        onError?.(e);
      }
    }, 1500);
  };

  const stop = () => {
    stopped = true;
    es?.close();
    if (timer) clearInterval(timer);
    timer = null;
  };

  try {
    if (typeof EventSource === "undefined") throw new Error("no EventSource");
    es = new EventSource(v5.jobs.eventsUrl(jid), { withCredentials: true });
    const handle = (ev: MessageEvent) => {
      try {
        const j = JSON.parse(ev.data) as Job;
        onJob(j);
        if (j.status === "done" || j.status === "failed") stop();
      } catch {}
    };
    for (const name of ["job.progress", "job.done", "job.failed"]) es.addEventListener(name, handle as EventListener);
    es.onmessage = handle;
    es.onerror = () => {
      es?.close();
      es = null;
      if (!stopped) poll();
    };
  } catch {
    poll();
  }
  return stop;
}

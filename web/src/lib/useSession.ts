"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, v5 } from "./api";
import type { SessionView } from "./types";

const POLL_MS = 1500;
const MAX_MS = 10000;
const SAFETY_MS = 8000;

/**
 * Live session state: SSE (`/api/sessions/{sid}/events`, event `session.state`) with a 1.5 s polling
 * fallback when EventSource is unavailable or errors (cookies blocked, proxies). A slow safety poll runs
 * beside the stream so a missed event never freezes a phone. `msUntil` uses the SERVER clock.
 */
export function useSession(sid: string | null) {
  const [view, setView] = useState<SessionView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<number | null>(null);
  const [skew, setSkew] = useState(0);
  const [transport, setTransport] = useState<"sse" | "poll" | "none">("none");
  const alive = useRef(true);
  const delay = useRef(POLL_MS);

  const apply = useCallback((v: SessionView) => {
    if (!alive.current) return;
    setView(v);
    setError(null);
    setStatus(200);
    if (v.server_time) {
      const st = Date.parse(v.server_time);
      if (!Number.isNaN(st)) setSkew(st - Date.now());
    }
  }, []);

  const fetchOnce = useCallback(async () => {
    if (!sid) return;
    try {
      apply(await v5.sessions.get(sid));
      delay.current = POLL_MS;
    } catch (e) {
      if (!alive.current) return;
      setError(e instanceof Error ? e.message : String(e));
      setStatus(e instanceof ApiError ? e.status : null);
      delay.current = Math.min(MAX_MS, delay.current * 2);
    }
  }, [sid, apply]);

  useEffect(() => {
    alive.current = true;
    if (!sid) return;
    let cancelled = false;
    let es: EventSource | null = null;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;
    let safety: ReturnType<typeof setInterval> | null = null;

    const pollLoop = async () => {
      if (cancelled) return;
      await fetchOnce();
      if (cancelled) return;
      pollTimer = setTimeout(pollLoop, delay.current);
    };
    const startPolling = () => {
      if (pollTimer) return;
      setTransport("poll");
      pollLoop();
    };

    fetchOnce();
    try {
      if (typeof EventSource === "undefined") throw new Error("no EventSource");
      es = new EventSource(v5.sessions.eventsUrl(sid), { withCredentials: true });
      es.addEventListener("session.state", ((ev: MessageEvent) => {
        try {
          apply(JSON.parse(ev.data) as SessionView);
          setTransport("sse");
        } catch {}
      }) as EventListener);
      es.onerror = () => {
        es?.close();
        es = null;
        if (!cancelled) startPolling();
      };
      safety = setInterval(() => {
        if (!cancelled && es) fetchOnce();
      }, SAFETY_MS);
    } catch {
      startPolling();
    }
    return () => {
      cancelled = true;
      alive.current = false;
      es?.close();
      if (pollTimer) clearTimeout(pollTimer);
      if (safety) clearInterval(safety);
    };
  }, [sid, fetchOnce, apply]);

  const msUntil = useCallback(
    (iso: string | null | undefined) => {
      if (!iso) return 0;
      const t = Date.parse(iso);
      return Number.isNaN(t) ? 0 : t - (Date.now() + skew);
    },
    [skew],
  );

  return { view, setView: apply, error, status, refresh: fetchOnce, msUntil, transport };
}

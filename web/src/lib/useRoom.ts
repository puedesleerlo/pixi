"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, getGuestId, Room } from "./api";

const BASE_MS = 1500;
const MAX_MS = 10000;

/**
 * Polls GET /api/rooms/{code}?guest_id= every 1.5 s (contract §5).
 * Exponential backoff on errors. `serverSkewMs` = server clock − local clock,
 * so countdowns can be computed against `round_ends_at` with the SERVER clock.
 */
export function useRoom(code: string | null, enabled = true) {
  const [room, setRoom] = useState<Room | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<number | null>(null);
  const [serverSkewMs, setServerSkewMs] = useState(0);
  const delayRef = useRef(BASE_MS);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const aliveRef = useRef(true);

  const fetchOnce = useCallback(async () => {
    if (!code) return;
    try {
      const r = await api.getRoom(code, getGuestId());
      if (!aliveRef.current) return;
      setRoom(r);
      setError(null);
      setStatus(200);
      if (r.server_time) {
        const st = Date.parse(r.server_time);
        if (!Number.isNaN(st)) setServerSkewMs(st - Date.now());
      }
      delayRef.current = BASE_MS;
    } catch (e) {
      if (!aliveRef.current) return;
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setStatus(e instanceof ApiError ? e.status : null);
      delayRef.current = Math.min(MAX_MS, delayRef.current * 2);
    }
  }, [code]);

  useEffect(() => {
    aliveRef.current = true;
    if (!code || !enabled) return;
    let cancelled = false;
    const loop = async () => {
      if (cancelled) return;
      await fetchOnce();
      if (cancelled) return;
      timerRef.current = setTimeout(loop, delayRef.current);
    };
    loop();
    return () => {
      cancelled = true;
      aliveRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [code, enabled, fetchOnce]);

  const refresh = useCallback(async () => {
    await fetchOnce();
  }, [fetchOnce]);

  /** Milliseconds remaining until an ISO server timestamp, using the server clock. */
  const msUntil = useCallback(
    (iso: string | null | undefined) => {
      if (!iso) return 0;
      const t = Date.parse(iso);
      if (Number.isNaN(t)) return 0;
      return t - (Date.now() + serverSkewMs);
    },
    [serverSkewMs],
  );

  return { room, setRoom, error, status, refresh, serverSkewMs, msUntil };
}

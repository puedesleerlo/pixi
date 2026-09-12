"use client";
import { useNow } from "@/lib/useNow";

/** Seconds left until a server timestamp, on the server clock. */
export default function Countdown({ endsAt, msUntil, className = "" }: { endsAt: string | null | undefined; msUntil: (iso: string | null | undefined) => number; className?: string }) {
  useNow(250);
  if (!endsAt) return null;
  const secs = Math.max(0, Math.ceil(msUntil(endsAt) / 1000));
  return <div className={`font-display text-3xl tabular-nums ${secs <= 10 ? "text-accent" : ""} ${className}`}>{secs}s</div>;
}

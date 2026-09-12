"use client";
import { useEffect, useRef, useState } from "react";
import CardFace from "@/components/CardFace";
import Dots from "@/components/Dots";
import type { Axes, PlacedElement } from "@/lib/api";
import { useNow } from "@/lib/useNow";

/**
 * Read: the composed card, eight rows of dots with ghost markers on a re-read, an optional
 * phrase, and the server countdown. Latency is measured from first paint to submit.
 */
export default function Read({
  elements,
  previousAxes,
  endsAt,
  msUntil,
  v,
  nCard,
  onSubmit,
}: {
  elements: PlacedElement[];
  previousAxes: Axes | null;
  endsAt: string | null;
  msUntil: (iso: string | null | undefined) => number;
  v: number;
  nCard?: number;
  onSubmit: (body: { axes: Axes; free_text?: string; latency_ms: number }) => Promise<void>;
}) {
  const [axes, setAxes] = useState<(number | null)[]>(Array(8).fill(null));
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const firstPaint = useRef<number>(0);
  useEffect(() => {
    firstPaint.current = performance.now();
  }, []);
  useNow(250);
  const remaining = endsAt ? Math.max(0, msUntil(endsAt)) : null;
  const secs = remaining === null ? null : Math.ceil(remaining / 1000);
  const expired = remaining !== null && remaining <= 0;
  const complete = axes.every((x) => x !== null);

  async function submit() {
    if (!complete) return;
    setBusy(true);
    setErr(null);
    try {
      await onSubmit({
        axes: axes.map((x) => x ?? 0),
        free_text: text.trim() ? text.trim().slice(0, 140) : undefined,
        latency_ms: Math.round(performance.now() - firstPaint.current),
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-col gap-4 pt-3">
      <header className="flex items-baseline justify-between">
        <div className="text-xs uppercase tracking-widest text-muted">
          {nCard ? `card ${nCard} · ` : ""}v{v} · what did you receive?
        </div>
        {secs !== null && <div className={`font-display text-2xl tabular-nums ${secs <= 10 ? "text-accent" : ""}`}>{secs}s</div>}
      </header>
      <CardFace elements={elements} size="big" className="mx-auto" />
      <p className="text-xs text-muted text-center -mt-1">
        {previousAxes ? (
          <>
            The card changed. Dashed rings are your previous answer — tap all eight again.
          </>
        ) : (
          <>
            Report what the card says to <em>you</em>. There is no right answer and you are not scored.
          </>
        )}
      </p>
      <Dots values={axes} ghosts={previousAxes} onChange={(i, val) => setAxes((a) => a.map((x, j) => (j === i ? val : x)))} disabled={expired} />
      <input
        value={text}
        onChange={(e) => setText(e.target.value.slice(0, 140))}
        maxLength={140}
        placeholder="Optional: a phrase for what you received"
        className="w-full border border-rule px-3 py-2 text-base"
        disabled={expired}
      />
      {err && <p className="text-sm text-accent">{err}</p>}
      <button onClick={submit} disabled={!complete || busy || expired} className="w-full bg-ink text-paper py-3 text-base tracking-wide sticky bottom-3">
        {expired ? "Time's up" : busy ? "Sending…" : complete ? "Submit" : `Submit (${axes.filter((x) => x !== null).length}/8)`}
      </button>
    </section>
  );
}

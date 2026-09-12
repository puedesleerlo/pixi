"use client";
import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import Dots from "@/components/Dots";
import CardImage from "./CardImage";
import SessionHeader from "./Header";
import { useNow } from "@/lib/useNow";
import type { Axes8, SessionView } from "@/lib/types";

/** Eight taps, no defaults, ghost markers on a re-read, an optional phrase, the server countdown. */
export default function Reader({ view, msUntil, names, onSubmit }: { view: SessionView; msUntil: (iso: string | null | undefined) => number; names?: Record<string, string>; onSubmit: (body: { axes: Axes8; free_text?: string; latency_ms: number }) => Promise<void> }) {
  const t = useTranslations("session");
  const [axes, setAxes] = useState<(number | null)[]>(Array(8).fill(null));
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const firstPaint = useRef<number>(0);
  useEffect(() => {
    firstPaint.current = performance.now();
    setAxes(Array(8).fill(null));
    setText("");
  }, [view.version?.id]);
  useNow(250);
  const remaining = view.round_ends_at ? Math.max(0, msUntil(view.round_ends_at)) : null;
  const expired = remaining !== null && remaining <= 0;
  const complete = axes.every((x) => x !== null);
  const ghosts = view.you.previous_axes ?? null;

  async function submit() {
    if (!complete) return;
    setBusy(true);
    setErr(null);
    try {
      await onSubmit({ axes: axes.map((x) => x ?? 0), free_text: text.trim() ? text.trim().slice(0, 140) : undefined, latency_ms: Math.round(performance.now() - firstPaint.current) });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-col gap-4 pt-3 pb-24">
      <SessionHeader view={view} msUntil={msUntil} title={t("readTitle")} />
      {view.version && <CardImage imageUrl={view.version.image_url} symbols={view.version.symbols_detected} names={names} size="big" className="mx-auto" />}
      <p className="text-xs text-muted text-center -mt-1">{ghosts ? t("ghostHint") : t("readHint")}</p>
      <Dots values={axes} ghosts={ghosts} onChange={(i, val) => setAxes((a) => a.map((x, j) => (j === i ? val : x)))} disabled={expired} />
      <input value={text} onChange={(e) => setText(e.target.value.slice(0, 140))} maxLength={140} placeholder={t("phrasePlaceholder")} className="w-full border border-rule px-3 py-2 text-base" disabled={expired} />
      {err && <p className="text-sm text-accent">{err}</p>}
      <div className="fixed left-0 right-0 bottom-0 bg-paper/95 backdrop-blur border-t border-rule px-4 py-3 z-20">
        <button onClick={submit} disabled={!complete || busy || expired} className="w-full max-w-md mx-auto block bg-ink text-paper py-3 text-base tracking-wide">
          {expired ? t("timesUp") : busy ? t("sending") : complete ? t("submit") : t("submitCount", { n: axes.filter((x) => x !== null).length })}
        </button>
      </div>
    </section>
  );
}

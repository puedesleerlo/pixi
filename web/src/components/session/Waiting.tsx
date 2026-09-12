"use client";
import Countdown from "./Countdown";
import CardImage from "./CardImage";
import type { SessionView } from "@/lib/types";

export default function Waiting({ view, msUntil, title, body, showCard = false, showCount = false, names }: { view: SessionView; msUntil: (iso: string | null | undefined) => number; title: string; body: string; showCard?: boolean; showCount?: boolean; names?: Record<string, string> }) {
  return (
    <section className="pt-8 flex flex-col items-center text-center gap-3">
      <h1 className="font-display text-2xl">{title}</h1>
      <p className="text-sm text-muted max-w-sm">{body}</p>
      {showCard && view.version && <CardImage imageUrl={view.version.image_url} symbols={view.version.symbols_detected} names={names} size="phone" />}
      <Countdown endsAt={view.round_ends_at} msUntil={msUntil} className="text-5xl mt-1" />
      {showCount && view.round && (
        <div className="text-sm">
          {view.round.n_submitted}/{view.round.n_readers}
        </div>
      )}
    </section>
  );
}

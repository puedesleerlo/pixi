"use client";
import { useTranslations } from "next-intl";
import Countdown from "./Countdown";
import CardImage from "./CardImage";
import type { SessionView } from "@/lib/types";

export default function Generating({ view, msUntil, names, onSkip, busy, pending }: { view: SessionView; msUntil: (iso: string | null | undefined) => number; names?: Record<string, string>; onSkip: () => void; busy: boolean; pending: string | null }) {
  const t = useTranslations("session");
  return (
    <section className="pt-8 flex flex-col items-center text-center gap-3">
      <h1 className="font-display text-2xl">{t("generatingTitle")}</h1>
      <p className="text-sm text-muted max-w-sm">{pending ?? t("generatingBody")}</p>
      {view.version && <CardImage imageUrl={view.version.image_url} symbols={view.version.symbols_detected} names={names} size="phone" className="opacity-60" />}
      <div className="w-full max-w-xs h-1 bg-rule overflow-hidden">
        <div className="h-full bg-ink animate-pulse" style={{ width: "60%" }} />
      </div>
      <Countdown endsAt={view.round_ends_at} msUntil={msUntil} className="text-5xl" />
      {view.you.is_host && (
        <button onClick={onSkip} disabled={busy} className="border border-ink px-4 py-2 text-sm">
          {t("skipGeneration")}
        </button>
      )}
    </section>
  );
}

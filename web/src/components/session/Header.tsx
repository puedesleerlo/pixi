"use client";
import { useTranslations } from "next-intl";
import Countdown from "./Countdown";
import type { SessionView } from "@/lib/types";

export default function SessionHeader({ view, msUntil, title, kicker }: { view: SessionView; msUntil: (iso: string | null | undefined) => number; title: string; kicker?: string }) {
  const t = useTranslations("session");
  const holder = view.players.find((p) => p.user_or_guest_id === (view.round?.maker_or_editor_id ?? view.current_maker_id))?.nickname;
  return (
    <header className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="text-xs uppercase tracking-widest text-muted truncate">
          {kicker ?? `${t("session")} ${view.code} · ${view.mode === "relay" ? t("relay") : t("readingRounds")}`}
          {view.card && ` · ${view.card.position_key ?? ""}${view.version ? ` v${view.version.v}` : ""}`}
          {holder && view.state !== "lobby" ? ` · ${t("held", { name: holder })}` : ""}
        </div>
        <h1 className="font-display text-2xl mt-1 leading-tight">{title}</h1>
      </div>
      <Countdown endsAt={view.round_ends_at} msUntil={msUntil} />
    </header>
  );
}

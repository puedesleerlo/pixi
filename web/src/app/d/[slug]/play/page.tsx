"use client";
import Link from "next/link";
import { useState } from "react";
import { useTranslations } from "next-intl";
import Share from "@/components/Share";
import { useDeckCtx } from "@/components/ws/DeckContext";
import { v5 } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export default function PlayPage() {
  const t = useTranslations("playws");
  const { deck, atLeast } = useDeckCtx();
  const sessions = useLoad(() => v5.decks.sessions(deck.id).catch(() => []), [deck.id]);
  const [mode, setMode] = useState<"reading" | "relay">("relay");
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      {atLeast("member") && (
        <section className="border border-rule p-4 flex flex-col gap-2 text-sm">
          <div className="font-display text-lg">{t("host")}</div>
          <div className="flex gap-2">
            {(["reading", "relay"] as const).map((m) => (
              <button key={m} type="button" onClick={() => setMode(m)} className={`border px-3 py-1 ${mode === m ? "border-ink bg-ink text-paper" : "border-rule"}`}>
                {t(`mode_${m}`)}
              </button>
            ))}
          </div>
          <button type="button" className="self-start bg-ink text-paper px-4 py-2" onClick={() => v5.decks.createSession(deck.id, { mode }).then((s) => (window.location.href = `/s/${s.code}`)).catch((e) => setErr(t("sessionsSoon") + ` (${e instanceof Error ? e.message : e})`))}>
            {t("start")}
          </button>
          {err && <p className="text-xs text-muted">{err}</p>}
        </section>
      )}
      <section>
        <div className="font-display text-lg mb-1">{t("queue")}</div>
        <p className="text-xs text-muted mb-2">{t("queueHint")}</p>
        <Share path={`/d/${deck.slug}/read`} />
      </section>
      <section>
        <div className="font-display text-lg mb-1">{t("sessions")}</div>
        <ul className="text-sm flex flex-col gap-1">
          {sessions.data?.map((s) => (
            <li key={s.id}>
              <Link href={`/s/${s.code}`} className="underline">
                {s.code}
              </Link>{" "}
              · {s.mode} · {s.state} · {s.players?.length ?? 0} {t("players")}
            </li>
          ))}
          {sessions.data?.length === 0 && <li className="text-muted">{t("noSessions")}</li>}
        </ul>
      </section>
    </div>
  );
}

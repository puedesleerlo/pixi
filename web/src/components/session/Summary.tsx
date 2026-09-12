"use client";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { AXES } from "@/lib/axes";
import type { SessionView } from "@/lib/types";

/** Session summary (spec §5.7): cards touched with shifts, bets and points; scores per player in join order. */
export default function Summary({ view, deckSlug, onEnd, busy }: { view: SessionView; deckSlug: string | null; onEnd: () => void; busy: boolean }) {
  const t = useTranslations("session");
  const s = view.summary;
  const points = (id: string) => view.scores?.[id] ?? 0;
  return (
    <section className="flex flex-col gap-6 pt-3">
      <header>
        <div className="text-xs uppercase tracking-widest text-muted">
          {t("session")} {view.code}
        </div>
        <h1 className="font-display text-2xl mt-1">{view.state === "ended" ? t("endedTitle") : t("summaryTitle")}</h1>
      </header>
      <div>
        <div className="text-xs uppercase tracking-widest text-muted mb-2">{t("pointsTitle")}</div>
        <ol className="border-t border-rule">
          {view.players.map((p) => (
            <li key={p.user_or_guest_id} className="flex justify-between border-b border-rule py-2 text-sm">
              <span>
                {p.nickname}
                {p.user_or_guest_id === view.you.id && <span className="text-muted"> ({t("you")})</span>}
              </span>
              <span className="tabular-nums">{p.role === "reader" ? <span className="text-muted text-xs">{t("readerNoScore")}</span> : `${points(p.user_or_guest_id)} pt`}</span>
            </li>
          ))}
        </ol>
        <p className="text-[11px] text-muted mt-1">{t("pointsNote")}</p>
      </div>
      <div>
        <div className="text-xs uppercase tracking-widest text-muted mb-2">{t("cardsTouched")}</div>
        <ul className="flex flex-col gap-2">
          {(s?.cards ?? []).map((c) => (
            <li key={c.round_id} className="border border-rule px-3 py-2 text-sm">
              <div className="flex justify-between">
                <span>
                  {c.kind === "edit" ? t("editBy", { name: c.actor ?? "?" }) : t("readOf", { name: c.actor ?? "?" })}
                  {deckSlug && (
                    <Link href={`/d/${deckSlug}/cards/${c.card_id}`} className="underline ml-2 text-xs text-muted">
                      {t("openCard")}
                    </Link>
                  )}
                </span>
                <span className="tabular-nums text-muted">F {c.fidelity === null ? "–" : c.fidelity.toFixed(2)}{c.delta_fidelity !== null ? ` (${c.delta_fidelity >= 0 ? "+" : ""}${c.delta_fidelity.toFixed(2)})` : ""}</span>
              </div>
              {c.bet !== null && c.bet !== undefined && (
                <div className="text-xs text-muted">
                  {t("bet")}: {AXES[c.bet][0]} ↔ {AXES[c.bet][1]} · {c.bet_hit === null ? "–" : c.bet_hit ? t("hit") : t("miss")}
                  {c.shift && ` · ${t("shift")} ${c.shift[c.bet] >= 0 ? "+" : ""}${c.shift[c.bet].toFixed(1)}`}
                </div>
              )}
              {c.landed && <div className="text-xs text-accent">{t("landed")}</div>}
              {c.scores.length > 0 && <div className="text-[11px] text-muted">{c.scores.map((x) => `${view.players.find((p) => p.user_or_guest_id === x.user_id)?.nickname ?? x.user_id} +${x.points} ${x.reason}`).join(" · ")}</div>}
            </li>
          ))}
          {(s?.cards ?? []).length === 0 && <li className="text-sm text-muted">{t("nothingYet")}</li>}
        </ul>
      </div>
      {view.state !== "ended" && view.you.is_host && (
        <button onClick={onEnd} disabled={busy} className="w-full bg-ink text-paper py-3 text-base tracking-wide">
          {t("endSession")}
        </button>
      )}
      {deckSlug && (
        <Link href={`/d/${deckSlug}/grammar`} className="text-sm underline underline-offset-2">
          {t("seeGrammar")}
        </Link>
      )}
    </section>
  );
}

"use client";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import SessionHeader from "./Header";
import { imageSrc, v5 } from "@/lib/api";
import type { Card, SessionView } from "@/lib/types";

/** Relay compose = the current maker picks an existing card (their own first); reading mode = the host picks. */
export default function ComposePick({ view, msUntil, onChoose, busy }: { view: SessionView; msUntil: (iso: string | null | undefined) => number; onChoose: (cardId: string) => void; busy: boolean }) {
  const t = useTranslations("session");
  const [cards, setCards] = useState<Card[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<"mine" | "all">("mine");
  const me = view.you.id;
  useEffect(() => {
    let cancelled = false;
    v5.cards
      .list(view.deck_id)
      .then((cs) => {
        if (!cancelled) setCards(cs.filter((c) => c.current_version_id && c.status !== "archived"));
      })
      .catch((e) => {
        if (!cancelled) {
          setCards([]);
          setErr(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [view.deck_id]);
  const mine = (cards ?? []).filter((c) => c.maker_id === me);
  const shown = filter === "mine" && mine.length > 0 ? mine : (cards ?? []);
  useEffect(() => {
    if (cards && mine.length === 0) setFilter("all");
  }, [cards, mine.length]);
  return (
    <section className="flex flex-col gap-4 pt-3">
      <SessionHeader view={view} msUntil={msUntil} title={view.mode === "relay" ? t("composeTitle") : t("pickTitle")} />
      <p className="text-sm text-muted">{view.mode === "relay" ? t("composeHint") : t("pickHint")}</p>
      {mine.length > 0 && (
        <div className="flex gap-2 text-xs">
          {(["mine", "all"] as const).map((f) => (
            <button key={f} type="button" onClick={() => setFilter(f)} className={`border px-2 py-1 ${filter === f ? "border-ink bg-ink text-paper" : "border-rule"}`}>
              {f === "mine" ? t("myCards") : t("allCards")}
            </button>
          ))}
        </div>
      )}
      {cards === null && <p className="text-sm text-muted">{t("loadingCards")}</p>}
      {err && <p className="text-xs text-accent">{t("cardsUnavailable")} ({err})</p>}
      {cards && shown.length === 0 && !err && <p className="text-sm text-muted">{t("noCards")}</p>}
      <ul className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {shown.map((c) => {
          const src = imageSrc(c.current_version?.thumb_url ?? c.current_version?.image_url ?? null);
          return (
            <li key={c.id}>
              <button type="button" disabled={busy} onClick={() => onChoose(c.id)} className="w-full text-left border border-rule hover:border-ink p-1.5 flex flex-col gap-1">
                <div className="w-full aspect-[11/19] bg-[#faf6ee] border border-rule flex items-center justify-center overflow-hidden">
                  {src ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={src} alt="" className="w-full h-full object-cover" loading="lazy" />
                  ) : (
                    <span className="text-[11px] text-muted px-2 text-center">{c.position_key}</span>
                  )}
                </div>
                <div className="text-xs leading-tight">
                  <span className="text-ink">{c.title || c.position_key}</span>
                  <span className="text-muted"> · {c.status}</span>
                </div>
                {c.maker_id === me && <div className="text-[10px] uppercase tracking-wider text-muted">{t("yours")}</div>}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

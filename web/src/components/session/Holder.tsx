"use client";
import { useTranslations } from "next-intl";
import { AxesMini } from "@/components/Dots";
import CardImage from "./CardImage";
import SessionHeader from "./Header";
import { AXES, axesToWords } from "@/lib/axes";
import type { Axes8, SessionView } from "@/lib/types";

/** The card's holder (maker or editor) while readers read: the sealed intent, the card, the count. */
export default function Holder({ view, msUntil, names, gaps }: { view: SessionView; msUntil: (iso: string | null | undefined) => number; names?: Record<string, string>; gaps?: Axes8 | null }) {
  const t = useTranslations("session");
  const order = gaps ? gaps.map((g, i) => ({ i, g })).sort((a, b) => Math.abs(b.g) - Math.abs(a.g)) : [];
  return (
    <section className="flex flex-col gap-4 pt-3">
      <SessionHeader view={view} msUntil={msUntil} title={t("holderTitle")} />
      <div className="flex gap-4 items-start">
        {view.version && <CardImage imageUrl={view.version.image_url} symbols={view.version.symbols_detected} names={names} size="phone" />}
        <div className="text-sm min-w-0 flex-1">
          {view.round && (
            <div className="font-display text-4xl tabular-nums">
              {view.round.n_submitted}
              <span className="text-lg text-muted">/{view.round.n_readers}</span>
            </div>
          )}
          <p className="text-xs text-muted">{t("holderBody")}</p>
        </div>
      </div>
      {view.intent && (
        <div className="border border-ink p-3 flex flex-col gap-2">
          <div className="text-[10px] uppercase tracking-widest text-muted">{t("intentPrivate")}</div>
          <p className="font-display text-lg leading-snug">“{view.intent.statement}”</p>
          <div className="text-xs text-muted">{axesToWords(view.intent.axes)}</div>
          <div className="max-w-sm">
            <AxesMini axes={view.intent.axes} />
          </div>
          {order.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-widest text-muted mt-1 mb-1">{t("pushToward")}</div>
              <ul className="text-xs flex flex-col gap-0.5">
                {order.slice(0, 4).map(({ i, g }) => (
                  <li key={i} className={`flex justify-between ${Math.abs(g) >= 1 ? "text-ink" : "text-muted"}`}>
                    <span>
                      {AXES[i][0]} ↔ {AXES[i][1]}
                    </span>
                    <span className="tabular-nums">
                      {g >= 0 ? "+" : ""}
                      {g.toFixed(1)}
                      {Math.abs(g) >= 0.5 && <span className="text-accent"> → {g > 0 ? AXES[i][1] : AXES[i][0]}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

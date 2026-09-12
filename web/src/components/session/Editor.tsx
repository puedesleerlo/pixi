"use client";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { AxesMini } from "@/components/Dots";
import CardImage from "./CardImage";
import SessionHeader from "./Header";
import { AXES, axesToWords } from "@/lib/axes";
import { imageSrc, v5 } from "@/lib/api";
import { useNow } from "@/lib/useNow";
import type { Axes8, SessionView, Symbol } from "@/lib/types";

type Op = "add" | "remove" | "replace";

/**
 * The live edit menu (spec §5.5, reduced): ONE op — add / remove / replace a symbol — a bet axis (chips
 * preloaded with the three largest current gaps) and a rationale. Posts /sessions/{sid}/edit.
 */
export default function Editor({
  view,
  msUntil,
  gaps,
  onSubmit,
  notice,
}: {
  view: SessionView;
  msUntil: (iso: string | null | undefined) => number;
  gaps: Axes8 | null;
  onSubmit: (body: { op: Op; symbol_id?: string | null; to_symbol_id?: string | null; placement?: string | null; bet_axis: number; rationale?: string }) => Promise<void>;
  notice: string | null;
}) {
  const t = useTranslations("session");
  const [symbols, setSymbols] = useState<Symbol[] | null>(null);
  const [op, setOp] = useState<Op | null>(null);
  const [onCard, setOnCard] = useState<string | null>(null);
  const [pick, setPick] = useState<string | null>(null);
  const [bet, setBet] = useState<number | null>(null);
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  useNow(250);
  useEffect(() => {
    let cancelled = false;
    v5.symbols
      .list(view.deck_id, "active")
      .then((s) => {
        if (!cancelled) setSymbols(s);
      })
      .catch(() => {
        if (!cancelled) setSymbols([]);
      });
    return () => {
      cancelled = true;
    };
  }, [view.deck_id]);
  const byId = useMemo(() => new Map((symbols ?? []).map((s) => [s.id, s])), [symbols]);
  const names = useMemo(() => Object.fromEntries((symbols ?? []).map((s) => [s.id, s.name])), [symbols]);
  const detected = [...(view.version?.symbols_detected ?? [])].sort((a, b) => b.salience - a.salience);
  const onCardIds = new Set(detected.map((d) => d.symbol_id));
  const remaining = view.round_ends_at ? Math.max(0, msUntil(view.round_ends_at)) : null;
  const expired = remaining !== null && remaining <= 0;
  const gapOrder = gaps ? gaps.map((g, i) => ({ i, g })).sort((a, b) => Math.abs(b.g) - Math.abs(a.g)) : [];
  const suggested = new Set(gapOrder.slice(0, 3).map((x) => x.i));
  const complete = op !== null && bet !== null && (op === "add" ? !!pick : op === "remove" ? !!onCard : !!onCard && !!pick);
  const candidates = (symbols ?? []).filter((s) => !onCardIds.has(s.id) && (!q || s.name.toLowerCase().includes(q.toLowerCase()) || s.key.toLowerCase().includes(q.toLowerCase())));

  function describe(): string {
    if (!op) return t("chooseMove");
    if (op === "add") return pick ? t("adding", { name: byId.get(pick)?.name ?? pick }) : t("pickSymbol");
    if (op === "remove") return onCard ? t("removing", { name: names[onCard] ?? onCard }) : t("tapOnCard");
    return onCard ? (pick ? t("replacing", { from: names[onCard] ?? onCard, to: byId.get(pick)?.name ?? pick }) : t("pickReplacement")) : t("tapToReplace");
  }

  async function submit() {
    if (!complete || op === null || bet === null) return;
    setBusy(true);
    setErr(null);
    try {
      await onSubmit({ op, symbol_id: op === "add" ? pick : onCard, to_symbol_id: op === "replace" ? pick : null, placement: op === "add" ? byId.get(pick ?? "")?.placement ?? null : null, bet_axis: bet, rationale: rationale.trim() || undefined });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <section className="flex flex-col gap-5 pt-3 pb-24">
      <SessionHeader view={view} msUntil={msUntil} title={t("editTitle")} />
      <p className="text-sm text-muted -mt-2">{t("editHint")}</p>
      {view.intent && (
        <div className="border border-ink p-3 flex flex-col gap-2">
          <div className="text-[10px] uppercase tracking-widest text-muted">{t("intentPrivate")}</div>
          <p className="font-display text-lg leading-snug">“{view.intent.statement}”</p>
          <div className="text-xs text-muted">{axesToWords(view.intent.axes)}</div>
          <div className="max-w-sm">
            <AxesMini axes={view.intent.axes} />
          </div>
          {gapOrder.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-widest text-muted mt-1 mb-1">{t("pushToward")}</div>
              <ul className="text-xs flex flex-col gap-0.5">
                {gapOrder.slice(0, 4).map(({ i, g }) => (
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

      <div className="flex gap-4 items-start">
        {view.version && <CardImage imageUrl={view.version.image_url} symbols={view.version.symbols_detected} names={names} size="phone" highlight={onCard} />}
        <div className="flex-1 flex flex-col gap-2 min-w-0">
          <div className="text-xs uppercase tracking-widest text-muted">{t("theMove")}</div>
          <div className="grid grid-cols-3 gap-1.5">
            {(["add", "remove", "replace"] as Op[]).map((o) => (
              <button
                key={o}
                type="button"
                disabled={expired}
                onClick={() => {
                  setOp(o);
                  setOnCard(null);
                  setPick(null);
                }}
                className={`border px-2 py-1.5 text-sm ${op === o ? "border-ink bg-ink text-paper" : "border-rule"}`}
              >
                {t(`op_${o}`)}
              </button>
            ))}
          </div>
          <div className="text-[11px] text-muted leading-relaxed">{describe()}</div>
          {(op === "remove" || op === "replace") && (
            <div className="flex flex-col gap-1">
              <div className="text-[10px] uppercase tracking-widest text-muted">{t("onTheCard")}</div>
              <div className="flex flex-wrap gap-1">
                {detected.map((d) => (
                  <button key={d.symbol_id} type="button" disabled={expired} onClick={() => setOnCard(d.symbol_id)} className={`border px-2 py-0.5 text-xs ${onCard === d.symbol_id ? "border-accent bg-accent text-paper" : "border-rule"}`}>
                    {names[d.symbol_id] ?? d.symbol_id} <span className="opacity-70">{d.salience.toFixed(1)}</span>
                  </button>
                ))}
                {detected.length === 0 && <span className="text-xs text-muted">{t("noSymbolsDetected")}</span>}
              </div>
            </div>
          )}
        </div>
      </div>

      {(op === "add" || (op === "replace" && onCard)) && (
        <div className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between">
            <div className="text-xs uppercase tracking-widest text-muted">{op === "add" ? t("symbolToAdd") : t("replacement")}</div>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="border border-rule px-2 py-1 text-xs w-32" />
          </div>
          {symbols === null && <p className="text-xs text-muted">{t("loadingSymbols")}</p>}
          <ul className="grid grid-cols-3 sm:grid-cols-4 gap-1.5 max-h-72 overflow-y-auto">
            {candidates.map((s) => {
              const src = imageSrc(s.exemplar?.image_url ?? null);
              const on = pick === s.id;
              return (
                <li key={s.id}>
                  <button type="button" disabled={expired} onClick={() => setPick(s.id)} className={`w-full text-left border p-1 flex flex-col gap-1 ${on ? "border-accent outline outline-1 outline-accent" : "border-rule"}`}>
                    <div className="w-full aspect-square bg-[#faf6ee] border border-rule flex items-center justify-center overflow-hidden">
                      {src ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={src} alt={s.name} className="w-full h-full object-contain" loading="lazy" />
                      ) : (
                        <span className="text-[10px] text-center px-1" style={{ fontVariant: "small-caps" }}>
                          {s.name}
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] leading-tight truncate">{s.name}</div>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <div className="text-xs uppercase tracking-widest text-muted">{t("betTitle")}</div>
        <p className="text-[11px] text-muted -mt-1">{t("betHint")}</p>
        <div className="grid grid-cols-2 gap-1">
          {AXES.map(([a, b], i) => (
            <button key={i} type="button" disabled={expired} onClick={() => setBet(i)} className={`border px-2 py-1.5 text-xs text-left ${bet === i ? "border-accent bg-accent text-paper" : suggested.has(i) ? "border-ink" : "border-rule"}`}>
              {a} ↔ {b}
              {suggested.has(i) && bet !== i && <span className="text-muted"> ·</span>}
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-col gap-1">
        <div className="text-xs uppercase tracking-widest text-muted">{t("rationale")}</div>
        <input value={rationale} onChange={(e) => setRationale(e.target.value.slice(0, 140))} maxLength={140} placeholder={t("rationalePlaceholder")} className="w-full border border-rule px-3 py-2 text-base" disabled={expired} />
      </div>
      {notice && <p className="text-sm border border-rule px-3 py-2">{notice}</p>}
      {err && <p className="text-sm text-accent">{err}</p>}
      <div className="fixed left-0 right-0 bottom-0 bg-paper/95 backdrop-blur border-t border-rule px-4 py-3 z-20">
        <button onClick={submit} disabled={!complete || busy || expired} className="w-full max-w-md mx-auto block bg-ink text-paper py-3 text-base tracking-wide">
          {expired ? t("timesUp") : busy ? t("sending") : complete ? t("makeChange") : !op ? t("chooseMove") : bet === null ? t("placeBet") : t("finishMove")}
        </button>
      </div>
    </section>
  );
}

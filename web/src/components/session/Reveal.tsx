"use client";
import { useTranslations } from "next-intl";
import GapBars from "@/components/GapBars";
import GrammarStrip from "@/components/GrammarStrip";
import RevealPlot from "@/components/RevealPlot";
import VerdictBadge from "@/components/VerdictBadge";
import CardImage from "./CardImage";
import SessionHeader from "./Header";
import type { GrammarStripItem, RevealReading, Verdict as VerdictV4 } from "@/lib/api";
import { AXES, axesToWords } from "@/lib/axes";
import type { SessionReveal, SessionView } from "@/lib/types";

function editedSymbolOf(how: SessionReveal["version"]["how"] | null | undefined): string | null {
  if (!how || !("op" in how)) return null;
  const e = how as { op?: string; symbol_id?: string | null; to_symbol_id?: string | null };
  return e.op === "replace" ? (e.to_symbol_id ?? e.symbol_id ?? null) : (e.symbol_id ?? null);
}

function toStrip(rows: SessionReveal["grammar_strip"]): GrammarStripItem[] {
  return rows.map((r) => ({
    element_id: r.symbol_id,
    label: r.name ?? r.key ?? r.symbol_id,
    salience: r.salience,
    coef: r.coef,
    ci_low: r.ci_low,
    ci_high: r.ci_high,
    n: r.n_readings,
    n_edits: r.n_edits,
    historical_support: r.drift_from_prior === null || r.drift_from_prior === undefined ? null : 1 - r.drift_from_prior,
  }));
}

export default function Reveal({ view, reveal, msUntil, names, onContinue, busy }: { view: SessionView; reveal: SessionReveal; msUntil: (iso: string | null | undefined) => number; names?: Record<string, string>; onContinue: () => void; busy: boolean }) {
  const t = useTranslations("session");
  const me = view.you.id;
  const isHolder = !!me && view.round?.maker_or_editor_id === me;
  const canContinue = view.you.is_host || isHolder;
  const v = reveal.version.v;
  const eff = reveal.edit_effect;
  const ms = reveal.maker_score;
  const how = reveal.version.how as { op?: string; symbol_id?: string | null; to_symbol_id?: string | null; rationale?: string | null; editor_id?: string | null } | null | undefined;
  const editedId = editedSymbolOf(reveal.version.how);
  const bet = eff?.bet_axis !== null && eff?.bet_axis !== undefined ? AXES[eff.bet_axis] : null;
  const editorNick = view.players.find((p) => p.user_or_guest_id === (eff?.editor_id ?? how?.editor_id))?.nickname ?? t("theEditor");
  const real = reveal.readings.filter((r) => !r.synthetic);
  const nSynth = reveal.readings.length - real.length;
  const plotReadings: RevealReading[] = reveal.readings.map((r, i) => ({
    reader_id: r.reader_id ?? (r.is_you && me ? me : `r${i}`),
    nickname: r.nickname ?? (r.is_you ? t("you") : `${t("reader")} ${i + 1}`),
    axes: r.axes,
    free_text: r.free_text,
    d_axes: r.d_axes,
    d_embed: r.d_embed,
    d_total: r.d_total,
    inside_radius: r.inside_radius,
    xy: r.xy,
    prev_xy: r.prev_xy ?? null,
    prev_axes: r.prev_axes ?? null,
    shift: r.shift ?? null,
    synthetic: r.synthetic,
  }));
  const gapBet = eff?.bet_axis ?? null;
  const yourD = reveal.you?.d_total ?? null;
  const done = reveal.card.status === "landed" || reveal.card.status === "closed";
  const scores = reveal.scores ?? [];
  const nick = (id: string) => view.players.find((p) => p.user_or_guest_id === id)?.nickname ?? id;
  return (
    <section className="flex flex-col gap-7 pt-3 pb-24">
      <SessionHeader view={view} msUntil={msUntil} title={v === 0 ? t("revealTitle0") : t("revealTitleN")} />

      <div className="flex gap-4 items-start">
        <CardImage imageUrl={reveal.version.image_url} symbols={reveal.version.symbols_detected} names={names} size="phone" highlight={editedId} />
        <div className="text-sm min-w-0 flex-1">
          <div className="text-xs uppercase tracking-widest text-muted">{t("cardOf", { name: view.card?.maker_nickname ?? "?" })}</div>
          {reveal.card.statement ? <p className="font-display text-lg leading-snug mt-1">“{reveal.card.statement}”</p> : <p className="text-xs text-muted mt-1">{t("sealed")}</p>}
          {how?.op && (
            <p className="text-sm mt-2">
              <span className="text-muted">v{v}:</span> {editorNick} {t(`did_${how.op}` as "did_add", { a: names?.[how.symbol_id ?? ""] ?? how.symbol_id ?? "", b: names?.[how.to_symbol_id ?? ""] ?? how.to_symbol_id ?? "" })}
              {how.rationale && <span className="italic text-muted"> — “{how.rationale}”</span>}
            </p>
          )}
          <div className="text-xs text-muted mt-2">
            {t("fidelity")} F {fmt(reveal.fidelity)}
            {reveal.fidelity_prev !== null && reveal.fidelity_prev !== undefined && (
              <>
                {" "}
                ({t("was")} {fmt(reveal.fidelity_prev)},{" "}
                <span className={(reveal.delta_fidelity ?? 0) > 0 ? "text-accent" : ""}>
                  ΔF {(reveal.delta_fidelity ?? 0) >= 0 ? "+" : ""}
                  {(reveal.delta_fidelity ?? 0).toFixed(2)}
                </span>
                )
              </>
            )}
          </div>
        </div>
      </div>

      <div>
        <div className="flex items-baseline justify-between">
          <h2 className="font-display text-lg">{t("plotTitle")}</h2>
          <span className="text-[11px] text-muted">
            ★ {t("intent")} · <span className="text-accent">●</span> {t("real")} · <span className="text-synth">●</span> {t("synthetic")}
            {v > 0 && ` · → ${t("shift")}`}
          </span>
        </div>
        {reveal.intent_xy ? (
          <>
            <RevealPlot intentXy={reveal.intent_xy} readings={plotReadings} radius={reveal.radius} youId={me} />
            <div className="text-[11px] text-muted mt-1">
              {t("plotNote")}
              {v > 0 && bet && (
                <>
                  {" "}
                  {t("arrowsNote", { v: v - 1, w: v })} <span className="text-ink">{bet[0]} ↔ {bet[1]}</span>.
                </>
              )}
            </div>
          </>
        ) : (
          <p className="text-sm text-muted border border-rule px-3 py-2 mt-1">{t("starHidden", { n: reveal.collecting.n, needed: reveal.collecting.threshold })}</p>
        )}
        {yourD !== null && (
          <div className="mt-2 border border-accent px-3 py-2 text-sm">
            {t("yourDistance")} <span className="font-display text-xl text-accent">{yourD.toFixed(2)}</span>
            <span className="text-muted text-xs"> · r = {reveal.radius.toFixed(2)}</span>
            {reveal.you?.shift && <span className="text-muted text-xs"> · {t("youMoved")} {axesToWords(reveal.you.shift, 2)}</span>}
          </div>
        )}
      </div>

      {reveal.gaps_abs && (
        <div className="border-t border-rule pt-4">
          <h2 className="font-display text-lg">{t("gapsTitle")}</h2>
          <p className="text-xs text-muted mb-2">{t("gapsHint")}</p>
          <GapBars gaps={reveal.gaps_abs} betAxis={gapBet} signed={reveal.gaps_signed ?? null} />
        </div>
      )}

      <div className="border-t border-rule pt-4 flex flex-col gap-3">
        {v === 0 && ms && (
          <div className="flex items-baseline gap-4">
            <div>
              <div className="text-xs uppercase tracking-widest text-muted">{t("makerScore")}</div>
              <div className="font-display text-5xl leading-none mt-1">
                {ms.points === null ? "–" : ms.points}
                <span className="text-lg text-muted"> pt</span>
              </div>
            </div>
            <div className="text-sm text-muted">{ms.n < ms.needs ? t("needsReaders", { needs: ms.needs, n: ms.n }) : t("scoreRule", { pct: Math.round((ms.f ?? 0) * 100), n: ms.n })}</div>
          </div>
        )}
        {v > 0 && eff && (
          <div className="flex items-baseline gap-4">
            <div>
              <div className="text-xs uppercase tracking-widest text-muted">{t("theBet")}</div>
              <div className={`font-display text-4xl leading-none mt-1 ${eff.bet_hit ? "text-accent" : ""}`}>{eff.bet_hit === null ? "–" : eff.bet_hit ? t("hit") : t("miss")}</div>
            </div>
            <div className="text-sm">
              {bet && (
                <>
                  {t("bet")}: <span className="text-ink">{bet[0]} ↔ {bet[1]}</span> ·{" "}
                </>
              )}
              {t("shift")}{" "}
              <span className="tabular-nums">{eff.shift && eff.bet_axis !== null ? `${eff.shift[eff.bet_axis] >= 0 ? "+" : ""}${eff.shift[eff.bet_axis].toFixed(1)}` : t("noPairs")}</span>
              {eff.gap_before && eff.bet_axis !== null && (
                <span className="text-muted">
                  {" "}
                  {t("vsGap")} {eff.gap_before[eff.bet_axis] >= 0 ? "+" : ""}
                  {eff.gap_before[eff.bet_axis].toFixed(1)}
                </span>
              )}
              {eff.bet_hit && <span className="text-accent"> · +2</span>}
              <div className="text-xs text-muted">{t("pairsNote", { n: eff.n_pairs })}</div>
            </div>
          </div>
        )}
        {reveal.landing?.landed && (
          <div className="border border-accent px-3 py-2 text-sm">
            <span className="font-display text-lg text-accent">{t("landed")}</span> F {fmt(reveal.fidelity)} ≥ {reveal.landing.threshold.toFixed(2)} · {t("landedPoints")}
          </div>
        )}
        {!reveal.card.landed && reveal.card.status === "closed" && <div className="text-sm text-muted">{t("closed", { n: reveal.card.max_edits })}</div>}
        {scores.length > 0 && (
          <div className="text-xs text-muted">
            {t("pointsThisRound")}: {scores.map((s) => `${nick(s.user_id)} +${s.points} (${s.reason})`).join(" · ")}
          </div>
        )}
      </div>

      <div>
        <h2 className="font-display text-lg">{t("receivedTitle")}</h2>
        <ul className="mt-2 flex flex-col gap-2">
          {real.map((r, i) => (
            <li key={`${r.reader_id ?? i}-${i}`} className="border-b border-rule pb-2">
              <div className="flex justify-between text-sm">
                <span>
                  {r.nickname ?? `${t("reader")} ${i + 1}`}
                  {r.is_you && <span className="text-muted"> ({t("you")})</span>}
                </span>
                <span className="text-muted text-xs">d {r.d_total.toFixed(2)}</span>
              </div>
              <div className="text-xs text-muted">{axesToWords(r.axes)}</div>
              {r.free_text && <div className="text-sm mt-0.5">“{r.free_text}”</div>}
            </li>
          ))}
          {real.length === 0 && <li className="text-sm text-muted">{t("noReadings")}</li>}
        </ul>
        {nSynth > 0 && <div className="text-[11px] text-synth mt-2">{t("syntheticNote", { n: nSynth })}</div>}
      </div>

      <div className="border-t border-rule pt-4">
        <h2 className="font-display text-lg">{t("verdictTitle")}</h2>
        <p className="text-xs text-muted mb-2">{t("verdictHint")}</p>
        <VerdictBadge verdict={reveal.verdict as unknown as VerdictV4} />
      </div>

      {reveal.grammar_strip.length > 0 && (
        <div className="border-t border-rule pt-4">
          <h2 className="font-display text-lg">{t("grammarTitle")}</h2>
          <p className="text-xs text-muted mb-3">{t("grammarHint")}</p>
          <GrammarStrip before={toStrip(reveal.grammar_strip_before)} after={toStrip(reveal.grammar_strip)} editedId={editedId} />
        </div>
      )}

      <div className="fixed left-0 right-0 bottom-0 bg-paper/95 backdrop-blur border-t border-rule px-4 py-3 z-20">
        <div className="max-w-md mx-auto flex flex-col gap-2">
          {canContinue ? (
            <button onClick={onContinue} disabled={busy} className="w-full bg-ink text-paper py-3 text-base tracking-wide">
              {view.mode === "reading" ? t("nextCard") : done ? t("nextMaker") : t("passToEditor")}
            </button>
          ) : (
            <p className="text-xs text-muted text-center">{t("continuesWhen")}</p>
          )}
        </div>
      </div>
    </section>
  );
}

function fmt(x: number | null | undefined) {
  return x === null || x === undefined ? "–" : x.toFixed(2);
}

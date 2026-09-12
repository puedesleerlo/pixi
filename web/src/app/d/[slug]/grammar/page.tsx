"use client";
import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import AxisBar from "@/components/AxisBar";
import ErrorState from "@/components/ErrorState";
import StatusChip from "@/components/StatusChip";
import { useDeckCtx } from "@/components/ws/DeckContext";
import { AXES } from "@/lib/axes";
import { v5 } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

const TABS = ["grammar", "coherence", "transmission"] as const;

function GrammarInner() {
  const t = useTranslations("grammarws");
  const { deck } = useDeckCtx();
  const sp = useSearchParams();
  const [tab, setTab] = useState<(typeof TABS)[number]>((sp.get("tab") as (typeof TABS)[number]) ?? "grammar");
  const [synthetic, setSynthetic] = useState(true);
  const [filter, setFilter] = useState<"all" | "drifting" | "contested" | "untested">("all");
  const grammar = useLoad(() => v5.decks.grammar(deck.id, synthetic), [deck.id, synthetic]);
  const coherence = useLoad(() => v5.decks.coherence(deck.id), [deck.id]);
  const rows = useMemo(
    () =>
      (grammar.data?.symbols ?? []).filter((r) =>
        filter === "drifting" ? (r.drift_from_prior ?? 0) > 0.5 : filter === "contested" ? r.coherence === "contested" : filter === "untested" ? (r.coherence ?? "untested") === "untested" : true,
      ),
    [grammar.data, filter],
  );
  const c = coherence.data;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2 text-sm">
        {TABS.map((k) => (
          <button key={k} type="button" onClick={() => setTab(k)} className={`border px-3 py-1 ${tab === k ? "border-ink bg-ink text-paper" : "border-rule"}`}>
            {t(`tab_${k}`)}
          </button>
        ))}
      </div>
      {tab === "grammar" && (
        <>
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <label className="flex items-center gap-1">
              <input type="checkbox" checked={synthetic} onChange={(e) => setSynthetic(e.target.checked)} /> {t("includeSynthetic")}
            </label>
            {(["all", "drifting", "contested", "untested"] as const).map((f) => (
              <button key={f} type="button" onClick={() => setFilter(f)} className={`border px-2 py-0.5 ${filter === f ? "border-ink bg-ink text-paper" : "border-rule"}`}>
                {t(`f_${f}`)}
              </button>
            ))}
            {grammar.data && (
              <span className="text-muted">
                n {grammar.data.n_readings} · {t("edits")} {grammar.data.n_edits ?? 0}
              </span>
            )}
          </div>
          {grammar.error && <ErrorState error={grammar.error} status={grammar.status} />}
          <div className="overflow-x-auto">
            <table className="text-[11px] min-w-[720px]">
              <thead>
                <tr className="text-[10px] uppercase tracking-wider text-muted">
                  <th className="text-left py-1 pr-2 w-32">{t("symbol")}</th>
                  {AXES.map(([l, r]) => (
                    <th key={l} className="text-center py-1 px-1 font-normal w-20">
                      {l}
                      <br />
                      {r}
                    </th>
                  ))}
                  <th className="py-1 pl-2">{t("edits")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.symbol_id} className="border-t border-rule">
                    <td className="py-1 pr-2">
                      <div>{r.name ?? r.symbol_id}</div>
                      <div className="text-muted">n {r.n_readings}</div>
                    </td>
                    {AXES.map((_, i) => (
                      <td key={i} className="px-1">
                        <AxisBar coef={r.coef[i]} lo={r.ci_low[i]} hi={r.ci_high[i]} prior={r.prior_axes?.[i] ?? null} effect={r.mean_effect?.[i] ?? null} height={12} />
                      </td>
                    ))}
                    <td className="pl-2 tabular-nums">{r.n_edits}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {grammar.data && rows.length === 0 && <p className="text-sm text-muted py-4">{t("empty")}</p>}
          </div>
        </>
      )}
      {tab === "coherence" && (
        <>
          {coherence.error && <ErrorState error={coherence.error} status={coherence.status} />}
          {c ? (
            <div className="grid sm:grid-cols-2 gap-4 text-sm">
              <div className="border border-rule p-3">
                <div className="text-[10px] uppercase tracking-widest text-muted">{t("index")}</div>
                <div className="font-display text-4xl">{c.coherence_index != null ? c.coherence_index.toFixed(2) : "—"}</div>
                <div className="text-xs text-muted">
                  {c.semantic.consistent} consistent · {c.semantic.contested} contested · {c.semantic.untested} untested
                </div>
              </div>
              <div className="border border-rule p-3">
                <div className="text-[10px] uppercase tracking-widest text-muted">{t("style")}</div>
                <div className="font-display text-2xl">{c.style.mean != null ? c.style.mean.toFixed(2) : "—"}</div>
                <ul className="text-xs">
                  {c.style.outliers.map((o) => (
                    <li key={o.card_id}>
                      {o.position_key ?? o.card_id} · {o.style_score.toFixed(2)}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="border border-rule p-3">
                <div className="text-[10px] uppercase tracking-widest text-muted">{t("structural")}</div>
                <div className="font-display text-2xl">
                  {c.structural.filled} / {c.structural.total}
                </div>
                <div className="text-xs text-muted">
                  {c.structural.drafts_without_intent} drafts without intent · {c.structural.closed_without_landing} closed without landing
                </div>
              </div>
              <div className="border border-rule p-3">
                <div className="text-[10px] uppercase tracking-widest text-muted">{t("contested")}</div>
                <ul className="text-xs">
                  {c.semantic.contested_symbols.map((s) => (
                    <li key={s.symbol_id} className="flex gap-2">
                      <StatusChip value="contested" />
                      {s.name ?? s.symbol_id} · {s.cards.map((x) => `${x.card_id.slice(-4)} ${x.angle.toFixed(0)}°`).join(", ")}
                    </li>
                  ))}
                  {c.semantic.contested_symbols.length === 0 && <li className="text-muted">—</li>}
                </ul>
              </div>
            </div>
          ) : (
            !coherence.error && <p className="text-sm text-muted">{t("empty")}</p>
          )}
        </>
      )}
      {tab === "transmission" && (
        <>
          {c ? (
            <div className="text-sm flex flex-col gap-3">
              <div>
                {t("meanFidelity")}: <b>{c.transmission.mean_fidelity != null ? c.transmission.mean_fidelity.toFixed(2) : "—"}</b> · {t("needsReadings")}: {c.transmission.needs_readings}
              </div>
              <div className="flex gap-2 text-xs">
                {Object.entries(c.transmission.verdicts ?? {}).map(([k, v]) => (
                  <span key={k} className="border border-rule px-2 py-1">
                    {k} {v}
                  </span>
                ))}
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-muted mb-1">{t("bandwidth")}</div>
                <svg viewBox="0 0 320 120" className="w-full max-w-md border border-rule bg-[#faf6ee]">
                  {[0, 0.5, 1].map((y) => (
                    <line key={y} x1={30} x2={310} y1={110 - y * 100} y2={110 - y * 100} stroke="#d9d2c3" />
                  ))}
                  {c.transmission.bandwidth.map((p, i, arr) => (
                    <g key={p.n_symbols}>
                      {i > 0 && <line x1={30 + (arr[i - 1].n_symbols / 6) * 280} y1={110 - arr[i - 1].mean_fidelity * 100} x2={30 + (p.n_symbols / 6) * 280} y2={110 - p.mean_fidelity * 100} stroke="#c8361e" />}
                      <circle cx={30 + (p.n_symbols / 6) * 280} cy={110 - p.mean_fidelity * 100} r={3} fill="#c8361e" />
                    </g>
                  ))}
                  <text x={160} y={118} fontSize={8} textAnchor="middle" fill="#6b6760">
                    {t("symbolsOnCard")}
                  </text>
                </svg>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted">{t("empty")}</p>
          )}
        </>
      )}
    </div>
  );
}

export default function GrammarPage() {
  return (
    <Suspense fallback={null}>
      <GrammarInner />
    </Suspense>
  );
}

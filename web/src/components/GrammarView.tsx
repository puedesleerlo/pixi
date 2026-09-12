"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AxisBar from "@/components/AxisBar";
import { api, BandwidthPoint, Grammar, GrammarElement } from "@/lib/api";
import { AXES } from "@/lib/axes";

/** The element × axis matrix for one deck, with CI bands, prior ticks, paired-effect markers. */
export default function GrammarView({ deckCode }: { deckCode: string }) {
  const [includeSynthetic, setIncludeSynthetic] = useState(true);
  const [driftOnly, setDriftOnly] = useState(false);
  const [grammar, setGrammar] = useState<Grammar | null>(null);
  const [bandwidth, setBandwidth] = useState<BandwidthPoint[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.deckBandwidth(deckCode).then((b) => alive && setBandwidth(b)).catch(() => {});
    return () => {
      alive = false;
    };
  }, [deckCode]);
  useEffect(() => {
    let alive = true;
    setGrammar(null);
    api
      .deckGrammar(deckCode, includeSynthetic)
      .then((g) => alive && setGrammar(g))
      .catch((e) => alive && setErr(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [deckCode, includeSynthetic]);

  const groups = useMemo(() => {
    if (!grammar) return [];
    const rows = grammar.elements.filter((e) => !driftOnly || (e.historical_support !== null && e.historical_support < 0));
    const byParent = new Map<string, GrammarElement[]>();
    for (const r of rows) {
      const k = r.origin === "generated" ? "generated · community library" : (r.parent_id ?? "other");
      if (!byParent.has(k)) byParent.set(k, []);
      byParent.get(k)!.push(r);
    }
    return [...byParent.entries()]
      .map(([pid, els]) => ({ pid, label: pretty(pid), els: els.sort((a, b) => a.label.localeCompare(b.label)) }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [grammar, driftOnly]);

  const axes = grammar?.axes?.length === 8 ? grammar.axes : AXES;

  return (
    <section className="pt-6 flex flex-col gap-6">
      <header>
        <div className="text-xs uppercase tracking-widest text-muted">the symbol grammar · deck {deckCode}</div>
        <h1 className="font-display text-3xl mt-1">What each symbol carries here</h1>
        <p className="text-sm text-muted mt-2 max-w-prose">
          Pooled ridge regression of every reading&apos;s eight scales on the slot salience of the symbols on the card read, scoped to this
          deck. Bands are 95% bootstrap intervals; ▾ is what the tradition (Waite 1911, Marseille) says a cut symbol means; ○ is the mean
          paired effect measured from one-symbol edits. Generated symbols have no tradition to drift from.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={includeSynthetic} onChange={(e) => setIncludeSynthetic(e.target.checked)} />
          include synthetic seeds
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={driftOnly} onChange={(e) => setDriftOnly(e.target.checked)} />
          drifting from tradition only
        </label>
        {grammar && (
          <span className="text-xs text-muted ml-auto">
            n <span className="text-accent">{grammar.n_real} real</span> · <span className="text-synth">{grammar.n_synthetic} synthetic</span> ·{" "}
            {grammar.n_readings} used{typeof grammar.n_edits === "number" && <> · {grammar.n_edits} edits</>}
          </span>
        )}
      </div>

      <div className="text-[11px] text-muted flex flex-wrap gap-x-3 gap-y-1">
        {axes.map(([l, r], i) => (
          <span key={i}>
            <span className="text-ink">{i + 1}</span> {l} ↔ {r}
          </span>
        ))}
      </div>

      {err && <p className="text-sm text-accent">Could not load the grammar: {err}</p>}
      {!grammar && !err && <p className="text-sm text-muted">Fitting…</p>}

      {grammar && (
        <div className="overflow-x-auto -mx-4 px-4">
          <table className="min-w-[820px] w-full border-collapse text-xs">
            <thead>
              <tr className="text-muted">
                <th className="text-left font-normal py-1 pr-2 w-44">symbol</th>
                {axes.map(([l, r], i) => (
                  <th key={i} className="font-normal px-1 py-1">
                    <div className="flex justify-between text-[10px]">
                      <span>{l}</span>
                      <span>{r}</span>
                    </div>
                  </th>
                ))}
                <th className="font-normal py-1 pl-2 text-right">edits</th>
                <th className="font-normal py-1 pl-2 text-right">trad.</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <GroupRows key={g.pid} label={g.label} els={g.els} />
              ))}
              {groups.length === 0 && (
                <tr>
                  <td colSpan={11} className="py-4 text-muted">
                    Nothing to show{driftOnly ? " — no symbol is drifting against the tradition yet" : ""}.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {bandwidth && bandwidth.length > 0 && (
        <div className="border-t border-rule pt-4">
          <h2 className="font-display text-lg">Symbolic bandwidth</h2>
          <p className="text-xs text-muted mb-2">Mean transmission fidelity vs. number of symbols on the card. Real readings only — adding a symbol is a spend.</p>
          <BandwidthChart points={bandwidth} />
        </div>
      )}

      <p className="text-xs text-muted">
        Card by card: <Link href={`/decks/${deckCode}`} className="underline underline-offset-2">the deck</Link>.
      </p>
    </section>
  );
}

function pretty(id: string) {
  return id.replace(/_/g, " ");
}

function GroupRows({ label, els }: { label: string; els: GrammarElement[] }) {
  return (
    <>
      <tr>
        <td colSpan={11} className="pt-4 pb-1 font-display text-sm border-b border-rule capitalize">
          {label}
        </td>
      </tr>
      {els.map((e) => (
        <tr key={e.element_id} className="border-b border-rule/60">
          <td className="py-1 pr-2 align-middle">
            <div className="text-ink">
              {e.label}
              {e.origin === "generated" && <span className="ml-1 text-[9px] border border-dashed border-ink px-1 text-muted">generated</span>}
              {e.origin === "tile" && <span className="ml-1 text-[9px] text-muted">tile</span>}
            </div>
            <div className="text-[10px] text-muted">n {e.n}</div>
          </td>
          {e.coef.map((c, i) => (
            <td key={i} className="px-1 py-1 align-middle">
              <AxisBar coef={c} lo={e.ci_low[i]} hi={e.ci_high[i]} prior={e.historical_prior?.[i] ?? null} effect={e.mean_effect?.[i] ?? null} height={16} />
            </td>
          ))}
          <td className="pl-2 text-right align-middle tabular-nums text-muted">{e.n_edits ?? 0}</td>
          <td className={`pl-2 text-right align-middle tabular-nums ${e.historical_support !== null && e.historical_support < 0 ? "text-accent" : ""}`}>
            {e.historical_support === null || e.historical_support === undefined ? <span className="text-muted">—</span> : `${e.historical_support >= 0 ? "+" : ""}${e.historical_support.toFixed(2)}`}
          </td>
        </tr>
      ))}
    </>
  );
}

function BandwidthChart({ points }: { points: BandwidthPoint[] }) {
  const W = 360;
  const H = 160;
  const pad = { l: 34, r: 10, t: 10, b: 26 };
  const xs = points.map((p) => p.n_elements);
  const xmin = Math.min(...xs);
  const xmax = Math.max(...xs, xmin + 1);
  const sx = (x: number) => pad.l + ((x - xmin) / (xmax - xmin)) * (W - pad.l - pad.r);
  const sy = (y: number) => pad.t + (1 - Math.max(0, Math.min(1, y))) * (H - pad.t - pad.b);
  const sorted = [...points].sort((a, b) => a.n_elements - b.n_elements);
  const d = sorted.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.n_elements).toFixed(1)},${sy(p.mean_fidelity).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-md h-auto">
      <line x1={pad.l} y1={sy(0)} x2={W - pad.r} y2={sy(0)} stroke="#d9d2c3" />
      <line x1={pad.l} y1={sy(1)} x2={pad.l} y2={sy(0)} stroke="#d9d2c3" />
      {[0, 0.5, 1].map((t) => (
        <text key={t} x={pad.l - 4} y={sy(t) + 3} fontSize={9} textAnchor="end" fill="#6b6760">
          {t.toFixed(1)}
        </text>
      ))}
      {sorted.map((p) => (
        <text key={p.n_elements} x={sx(p.n_elements)} y={H - 8} fontSize={9} textAnchor="middle" fill="#6b6760">
          {p.n_elements}
        </text>
      ))}
      <text x={W / 2} y={H} fontSize={9} textAnchor="middle" fill="#6b6760">
        symbols on the card
      </text>
      <path d={d} fill="none" stroke="#c8361e" strokeWidth={1.5} />
      {sorted.map((p) => (
        <circle key={p.n_elements} cx={sx(p.n_elements)} cy={sy(p.mean_fidelity)} r={3} fill="#c8361e">
          <title>
            {p.n_elements} symbols · fidelity {p.mean_fidelity.toFixed(2)} · {p.n_cards} cards
          </title>
        </circle>
      ))}
    </svg>
  );
}

"use client";
import { useEffect, useState } from "react";
import { AXES } from "@/lib/axes";
import type { GrammarStripItem } from "@/lib/api";
import AxisBar from "./AxisBar";

/**
 * The grammar strip for the elements on a version. Mounts with `before` values and, after a
 * beat, transitions to `after` — the CI band visibly narrows (or widens, honestly).
 * The edited element, when given, is listed first and marked.
 */
export default function GrammarStrip({
  before,
  after,
  editedId = null,
  delayMs = 900,
}: {
  before: GrammarStripItem[];
  after: GrammarStripItem[];
  editedId?: string | null;
  delayMs?: number;
}) {
  const [phase, setPhase] = useState<"before" | "after">(before.length ? "before" : "after");
  useEffect(() => {
    if (!before.length) {
      setPhase("after");
      return;
    }
    setPhase("before");
    const t = setTimeout(() => setPhase("after"), delayMs);
    return () => clearTimeout(t);
  }, [before, after, delayMs]);

  const beforeById = new Map(before.map((b) => [b.element_id, b]));
  const items = [...(after.length ? after : before)].sort((a, b) => (a.element_id === editedId ? -1 : b.element_id === editedId ? 1 : 0));
  if (!items.length) return <p className="text-sm text-muted">No elements on this card.</p>;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between text-xs text-muted">
        <span>{phase === "before" ? "before this read" : "after this read"} · 95% bootstrap CI</span>
        <span>▾ historical prior</span>
      </div>
      {items.map((el) => {
        const b = beforeById.get(el.element_id);
        const cur = phase === "before" && b ? b : el;
        const widthBefore = b ? avgWidth(b) : null;
        const widthAfter = avgWidth(el);
        const edited = el.element_id === editedId;
        return (
          <div key={el.element_id} className={`border-t pt-2 ${edited ? "border-accent" : "border-rule"}`}>
            <div className="flex items-baseline justify-between gap-2 flex-wrap">
              <div className="font-display text-base">
                {el.label}
                {edited && <span className="ml-2 text-[10px] uppercase tracking-wider text-accent">edited</span>}
                {el.origin === "generated" && <span className="ml-2 text-[10px] border border-dashed border-ink px-1 text-muted">generated</span>}
              </div>
              <div className="text-[11px] text-muted whitespace-nowrap">
                {el.slot ? `${el.slot} · ` : ""}salience {el.salience.toFixed(1)} · n {cur.n}
                {typeof el.n_edits === "number" && el.n_edits > 0 && <> · edits {el.n_edits}</>}
                {widthBefore !== null && (
                  <>
                    {" "}
                    · band {widthBefore.toFixed(2)} →{" "}
                    <span className={widthAfter < widthBefore ? "text-accent" : ""}>{widthAfter.toFixed(2)}</span>
                  </>
                )}
                {" · "}
                tradition{" "}
                {el.historical_support === null || el.historical_support === undefined ? (
                  <span>no attestation</span>
                ) : (
                  <span className={el.historical_support < 0 ? "text-accent" : ""}>
                    {el.historical_support >= 0 ? "+" : ""}
                    {el.historical_support.toFixed(2)}
                  </span>
                )}
              </div>
            </div>
            <div className="mt-1 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-0.5">
              {AXES.map(([l, r], i) => (
                <div key={i} className="flex items-center gap-1 text-[10px] text-muted">
                  <span className="w-16 text-right truncate">{l}</span>
                  <AxisBar coef={cur.coef[i]} lo={cur.ci_low[i]} hi={cur.ci_high[i]} height={12} className="flex-1" />
                  <span className="w-16 text-left truncate">{r}</span>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function avgWidth(it: GrammarStripItem): number {
  let s = 0;
  for (let i = 0; i < it.coef.length; i++) s += Math.abs(it.ci_high[i] - it.ci_low[i]);
  return s / Math.max(1, it.coef.length);
}

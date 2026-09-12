"use client";
import { AxesMini } from "@/components/Dots";
import type { IntentView } from "@/lib/api";
import { AXES, axesToWords } from "@/lib/axes";

/** The holder's private view of the intent: statement, scales, and the signed gaps with the direction to push. */
export default function IntentPanel({ intent, compact = false }: { intent: IntentView; compact?: boolean }) {
  const gaps = intent.gaps_signed;
  const order = gaps ? gaps.map((g, i) => ({ i, g })).sort((a, b) => Math.abs(b.g) - Math.abs(a.g)) : [];
  return (
    <div className="border border-ink p-3 flex flex-col gap-2">
      <div className="text-[10px] uppercase tracking-widest text-muted">the intent · only you see this</div>
      <p className="font-display text-lg leading-snug">“{intent.statement}”</p>
      <div className="text-xs text-muted">{axesToWords(intent.axes)}</div>
      {!compact && (
        <div className="max-w-sm">
          <AxesMini axes={intent.axes} />
        </div>
      )}
      {gaps && (
        <div>
          <div className="text-[10px] uppercase tracking-widest text-muted mt-1 mb-1">where the room missed · push toward</div>
          <ul className="text-xs flex flex-col gap-0.5">
            {order.slice(0, compact ? 3 : 8).map(({ i, g }) => (
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
  );
}

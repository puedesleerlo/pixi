"use client";
import { AXES } from "@/lib/axes";
import type { GapAbs } from "@/lib/api";

/** Eight sorted bars of |g_k| (contract §6.2): where the room missed the intent. */
export default function GapBars({ gaps, betAxis = null, signed = null }: { gaps: GapAbs[]; betAxis?: number | null; signed?: number[] | null }) {
  const sorted = [...gaps].sort((a, b) => b.abs - a.abs);
  return (
    <div className="flex flex-col gap-1.5">
      {sorted.map((g, i) => {
        const [l, r] = AXES[g.axis];
        const pct = Math.min(100, (g.abs / 6) * 100);
        const isBet = betAxis === g.axis;
        const s = signed ? signed[g.axis] : null;
        return (
          <div key={g.axis} className="flex items-center gap-2 text-[11px]">
            <span className={`w-32 text-right truncate ${isBet ? "text-accent" : i === 0 ? "text-ink" : "text-muted"}`}>
              {l} ↔ {r}
            </span>
            <div className="relative flex-1 h-[10px] border border-rule">
              <div className="absolute inset-y-0 left-0" style={{ width: `${pct}%`, background: isBet ? "#c8361e" : "#141414", opacity: isBet ? 0.9 : 0.75 }} />
            </div>
            <span className={`w-14 tabular-nums ${isBet ? "text-accent" : "text-muted"}`}>
              {s !== null && s !== undefined ? `${s >= 0 ? "+" : ""}${s.toFixed(1)}` : g.abs.toFixed(1)}
              {isBet && " bet"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

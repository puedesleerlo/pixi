import { AXES } from "@/lib/axes";
import type { Axes8 } from "@/lib/types";

/** Eight tiny horizontal bars from −3..3 (declared or measured meaning), optional CI band and prior ticks. */
export default function MiniBars({
  axes,
  lo,
  hi,
  prior,
  color = "#141414",
  width = 96,
  labels = false,
}: {
  axes: Axes8;
  lo?: Axes8 | null;
  hi?: Axes8 | null;
  prior?: Axes8 | null;
  color?: string;
  width?: number;
  labels?: boolean;
}) {
  const pct = (v: number) => ((Math.max(-3, Math.min(3, v)) + 3) / 6) * 100;
  return (
    <div className="flex flex-col gap-[2px]" style={{ width }} aria-label="eight scales">
      {AXES.map(([l, r], i) => {
        const v = axes?.[i] ?? 0;
        const hasCi = lo && hi && lo[i] !== undefined && hi[i] !== undefined;
        return (
          <div key={i} className="flex items-center gap-1">
            {labels && <span className="w-12 text-[9px] text-muted text-right truncate">{l}</span>}
            <div className="relative flex-1 h-[5px] bg-[#e9e3d6]" title={`${l} ↔ ${r}: ${v.toFixed(1)}`}>
              <span className="absolute top-0 bottom-0 left-1/2 w-px bg-rule" />
              {hasCi && (
                <span className="absolute top-0 bottom-0 opacity-30" style={{ left: `${pct(Math.min(lo![i], hi![i]))}%`, width: `${Math.max(1, pct(Math.max(lo![i], hi![i])) - pct(Math.min(lo![i], hi![i])))}%`, background: color }} />
              )}
              <span className="absolute -top-[1px] w-[3px] h-[7px]" style={{ left: `calc(${pct(v)}% - 1px)`, background: color }} />
              {prior && prior[i] !== undefined && <span className="absolute -bottom-[3px] text-[7px] leading-none" style={{ left: `calc(${pct(prior[i])}% - 3px)` }}>▾</span>}
            </div>
            {labels && <span className="w-12 text-[9px] text-muted truncate">{r}</span>}
          </div>
        );
      })}
    </div>
  );
}

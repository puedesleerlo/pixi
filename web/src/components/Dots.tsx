"use client";
import { AXES } from "@/lib/axes";

const VALUES = [-3, -2, -1, 0, 1, 2, 3];

/**
 * One bipolar row: pole labels on the line above the dots so seven 40 px hit areas fit a
 * 375 px phone with no horizontal scroll. No default value. `ghost` draws a hollow ring at a
 * previous answer (re-reads, contract §6.1) — it is never a prefill.
 */
export function DotRow({
  index,
  value,
  ghost = null,
  onChange,
  disabled = false,
  compact = false,
}: {
  index: number;
  value: number | null;
  ghost?: number | null;
  onChange?: (v: number) => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  const [left, right] = AXES[index];
  const hit = compact ? 34 : 40;
  return (
    <div className={compact ? "py-0.5" : "py-1"}>
      <div className="flex justify-between text-[12px] leading-none px-1">
        <span className={value !== null && value < 0 ? "text-ink font-medium" : "text-muted"}>{left}</span>
        <span className={value !== null && value > 0 ? "text-ink font-medium" : "text-muted"}>{right}</span>
      </div>
      <div className="flex justify-between items-center">
        {VALUES.map((v) => {
          const selected = value === v;
          const isGhost = ghost !== null && ghost !== undefined && Math.round(ghost) === v;
          const r = v === 0 ? 5 : Math.abs(v) === 1 ? 6 : Math.abs(v) === 2 ? 7.5 : 9;
          return (
            <button
              key={v}
              type="button"
              aria-label={`${v < 0 ? left : v > 0 ? right : "neutral"} ${Math.abs(v)}${isGhost ? " (your previous answer)" : ""}`}
              aria-pressed={selected}
              disabled={disabled}
              onClick={() => onChange?.(v)}
              className="relative flex items-center justify-center"
              style={{ width: hit, height: hit }}
            >
              {isGhost && (
                <span
                  className="absolute rounded-full border border-dashed border-ink opacity-60"
                  style={{ width: r * 2 + 10, height: r * 2 + 10 }}
                />
              )}
              <span
                className={`block rounded-full border-2 ${selected ? "bg-accent border-accent" : "border-ink bg-transparent"}`}
                style={{ width: r * 2, height: r * 2 }}
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** All eight rows. `values` has nulls until tapped; `ghosts` are previous answers (optional). */
export default function Dots({
  values,
  ghosts,
  onChange,
  disabled = false,
  compact = false,
}: {
  values: (number | null)[];
  ghosts?: (number | null)[] | null;
  onChange?: (i: number, v: number) => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  return (
    <div className="w-full max-w-sm mx-auto">
      {AXES.map((_, i) => (
        <DotRow
          key={i}
          index={i}
          value={values[i] ?? null}
          ghost={ghosts?.[i] ?? null}
          onChange={(v) => onChange?.(i, v)}
          disabled={disabled}
          compact={compact}
        />
      ))}
    </div>
  );
}

/** Read-only miniature of an axis vector. */
export function AxesMini({ axes, color = "#141414", highlight = null }: { axes: number[]; color?: string; highlight?: number | null }) {
  return (
    <div className="flex flex-col gap-[3px]">
      {AXES.map(([l, r], i) => {
        const v = axes[i] ?? 0;
        const pct = ((v + 3) / 6) * 100;
        const hi = highlight === i;
        return (
          <div key={i} className={`flex items-center gap-1 text-[10px] ${hi ? "text-ink" : "text-muted"}`}>
            <span className="w-14 text-right truncate">{l}</span>
            <div className="relative flex-1 h-[6px] border-y border-rule">
              <span className="absolute top-0 bottom-0 left-1/2 w-px bg-rule" />
              <span
                className="absolute -top-[2px] w-[10px] h-[10px] rounded-full"
                style={{ left: `calc(${pct}% - 5px)`, background: hi ? "#c8361e" : color }}
              />
            </div>
            <span className="w-14 text-left truncate">{r}</span>
          </div>
        );
      })}
    </div>
  );
}

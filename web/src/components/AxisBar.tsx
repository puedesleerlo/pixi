"use client";
/**
 * One horizontal bar from −3..3 with a CI band, a coefficient tick, an optional prior tick (▾)
 * and an optional paired-effect marker (○). `.band` / `.tick` carry 2.5 s CSS transitions so
 * a change of props animates — the narrowing band is the hero animation.
 */
export default function AxisBar({
  coef,
  lo,
  hi,
  prior,
  effect,
  color = "#c8361e",
  height = 14,
  className = "",
}: {
  coef: number;
  lo: number;
  hi: number;
  prior?: number | null;
  effect?: number | null;
  color?: string;
  height?: number;
  className?: string;
}) {
  const pct = (v: number) => ((Math.max(-3, Math.min(3, v)) + 3) / 6) * 100;
  const l = pct(Math.min(lo, hi));
  const w = Math.max(0.8, pct(Math.max(lo, hi)) - l);
  return (
    <div className={`relative w-full ${className}`} style={{ height }}>
      <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-px bg-rule" />
      <div className="absolute top-0 bottom-0 left-1/2 w-px bg-rule" />
      <div
        className="band absolute top-[3px] bottom-[3px] rounded-sm"
        style={{ left: `${l}%`, width: `${w}%`, background: color, opacity: 0.28 }}
      />
      <div className="tick absolute top-0 bottom-0 w-[2px]" style={{ left: `calc(${pct(coef)}% - 1px)`, background: color }} />
      {prior !== undefined && prior !== null && (
        <div
          className="absolute top-[-2px] w-0 h-0"
          style={{
            left: `calc(${pct(prior)}% - 4px)`,
            borderLeft: "4px solid transparent",
            borderRight: "4px solid transparent",
            borderTop: "6px solid #141414",
          }}
          title={`historical prior ${prior.toFixed(1)}`}
        />
      )}
      {effect !== undefined && effect !== null && (
        <div
          className="absolute rounded-full border border-ink bg-paper"
          style={{ left: `calc(${pct(effect)}% - 4px)`, top: height / 2 - 4, width: 8, height: 8 }}
          title={`mean paired edit effect ${effect.toFixed(2)}`}
        />
      )}
    </div>
  );
}

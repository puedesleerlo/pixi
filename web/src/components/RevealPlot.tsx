"use client";
import type { RevealReading } from "@/lib/api";

const ACCENT = "#c8361e";
const SYNTH = "#9b9b93";
const INK = "#141414";
const RULE = "#d9d2c3";

/**
 * Frozen-PCA plane (contract §6.9): intent = star, readings = dots, radius r drawn as a circle.
 * On v ≥ 1 an arrow per reader runs from the previous reading to the new one (drawn slowly).
 * Dots are filled when inside_radius (8-d truth) and hollow otherwise.
 */
export default function RevealPlot({
  intentXy,
  readings,
  radius,
  youId,
  size = 320,
}: {
  intentXy: [number, number];
  readings: RevealReading[];
  radius: number;
  youId: string | null;
  size?: number;
}) {
  const rUnits = radius * 6 * Math.sqrt(8);
  let maxD = rUnits * 1.05;
  for (const rd of readings) {
    const d = Math.hypot(rd.xy[0] - intentXy[0], rd.xy[1] - intentXy[1]);
    if (d > maxD) maxD = d;
    if (rd.prev_xy) {
      const p = Math.hypot(rd.prev_xy[0] - intentXy[0], rd.prev_xy[1] - intentXy[1]);
      if (p > maxD) maxD = p;
    }
  }
  const half = maxD * 1.12 + 0.3;
  const scale = size / 2 / half;
  const cx = size / 2;
  const cy = size / 2;
  const sx = (x: number) => cx + (x - intentXy[0]) * scale;
  const sy = (y: number) => cy - (y - intentXy[1]) * scale;
  const hasArrows = readings.some((r) => !!r.prev_xy);

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full h-auto max-w-[420px] mx-auto block" role="img" aria-label="Readings plotted against the intent">
      <defs>
        <marker id="arrowhead" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="userSpaceOnUse">
          <path d="M0,0 L8,4 L0,8 z" fill={ACCENT} />
        </marker>
      </defs>
      <rect x={0} y={0} width={size} height={size} fill="none" stroke={RULE} />
      <line x1={0} y1={cy} x2={size} y2={cy} stroke={RULE} strokeDasharray="2 4" />
      <line x1={cx} y1={0} x2={cx} y2={size} stroke={RULE} strokeDasharray="2 4" />
      <circle cx={cx} cy={cy} r={rUnits * scale} fill="none" stroke={INK} strokeDasharray="4 4" opacity={0.6} />
      <text x={cx + rUnits * scale * 0.72} y={cy - rUnits * scale * 0.72} fontSize={10} fill={INK} opacity={0.7}>
        r = {radius.toFixed(2)}
      </text>
      {/* previous positions + arrows (v ≥ 1) */}
      {hasArrows &&
        readings.map((rd, i) => {
          if (!rd.prev_xy) return null;
          const x0 = sx(rd.prev_xy[0]);
          const y0 = sy(rd.prev_xy[1]);
          const x1 = sx(rd.xy[0]);
          const y1 = sy(rd.xy[1]);
          const len = Math.hypot(x1 - x0, y1 - y0);
          // stop the shaft short of the dot so the head is visible
          const k = len > 8 ? (len - 7) / len : 0;
          return (
            <g key={`arrow-${rd.reader_id}-${i}`}>
              <circle cx={x0} cy={y0} r={4} fill="none" stroke={rd.synthetic ? SYNTH : ACCENT} strokeWidth={1} opacity={0.5} />
              {len > 2 && (
                <line
                  className="shift-arrow"
                  x1={x0}
                  y1={y0}
                  x2={x0 + (x1 - x0) * k}
                  y2={y0 + (y1 - y0) * k}
                  stroke={rd.synthetic ? SYNTH : ACCENT}
                  strokeWidth={1.6}
                  markerEnd="url(#arrowhead)"
                  pathLength={1}
                />
              )}
            </g>
          );
        })}
      {readings.map((rd, i) => {
        const x = sx(rd.xy[0]);
        const y = sy(rd.xy[1]);
        const color = rd.synthetic ? SYNTH : ACCENT;
        const you = youId !== null && rd.reader_id === youId;
        return (
          <g key={`${rd.reader_id}-${i}`}>
            {you && <circle cx={x} cy={y} r={11} fill="none" stroke={ACCENT} strokeWidth={1.5} />}
            <circle cx={x} cy={y} r={rd.synthetic ? 3.5 : 5.5} fill={rd.inside_radius ? color : "#f4efe6"} stroke={color} strokeWidth={1.8}>
              <title>
                {rd.nickname} · d = {rd.d_total.toFixed(2)}
              </title>
            </circle>
            {!rd.synthetic && (
              <text x={x + 8} y={y + 3} fontSize={9} fill={INK} opacity={0.8}>
                {rd.nickname}
              </text>
            )}
          </g>
        );
      })}
      <polygon points={star(cx, cy, 11, 5)} fill={INK} stroke="#f4efe6" strokeWidth={1} />
    </svg>
  );
}

function star(cx: number, cy: number, R: number, r: number): string {
  const pts: string[] = [];
  for (let k = 0; k < 10; k++) {
    const rad = k % 2 === 0 ? R : r;
    const a = (Math.PI / 5) * k - Math.PI / 2;
    pts.push(`${(cx + rad * Math.cos(a)).toFixed(2)},${(cy + rad * Math.sin(a)).toFixed(2)}`);
  }
  return pts.join(" ");
}

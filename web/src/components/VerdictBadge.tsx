import type { Verdict } from "@/lib/api";
import Badge from "./Badge";

export function verdictTone(v: Verdict["verdict"]) {
  return v === "polysemous" ? "accent" : v === "legible" ? "ink" : v === "noisy" ? "muted" : "outline";
}

export default function VerdictBadge({ verdict, showStats = true }: { verdict: Verdict; showStats?: boolean }) {
  if (verdict.verdict === "collecting") {
    return (
      <div className="flex flex-col gap-1">
        <Badge tone="outline">collecting · {verdict.n}/{verdict.needed ?? 8}</Badge>
        <span className="text-xs text-muted">The verdict needs eight readings before it says anything.</span>
      </div>
    );
  }
  const desc =
    verdict.verdict === "legible"
      ? "reads one way"
      : verdict.verdict === "polysemous"
        ? `reads ${verdict.k ?? 2} coherent ways — a rich card`
        : "the card does not signify — readings scatter as noise";
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2 flex-wrap">
        <Badge tone={verdictTone(verdict.verdict)}>{verdict.verdict}</Badge>
        <span className="text-sm">{desc}</span>
      </div>
      {showStats && (
        <div className="text-[11px] text-muted font-mono">
          n {verdict.n} · V {fmt(verdict.V)} · S {fmt(verdict.S)} · S<sub>null95</sub> {fmt(verdict.S_null95)}
          {verdict.P !== undefined && <> · P {fmt(verdict.P)}</>}
        </div>
      )}
      {verdict.clusters && verdict.verdict === "polysemous" && (
        <ul className="flex flex-wrap gap-2 mt-0.5">
          {verdict.clusters.map((c, i) => (
            <li key={i} className="text-xs border border-rule px-2 py-1">
              <span className="font-display text-sm">{c.label ?? `cluster ${i + 1}`}</span>
              <span className="text-muted">
                {" "}
                · n {c.n} · {c.label_by === "k2" ? "named by K2" : "template name"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function fmt(x: number | undefined) {
  return x === undefined || x === null ? "–" : x.toFixed(2);
}

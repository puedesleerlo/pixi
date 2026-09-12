"use client";
import Link from "next/link";
import CardFace from "@/components/CardFace";
import Badge from "@/components/Badge";
import type { Chain as ChainT } from "@/lib/api";
import { AXES } from "@/lib/axes";
import { moveWords } from "@/lib/slots";

/**
 * A card's chain (contract §9): v0 face → one row per edit (editor, move, bet, rationale,
 * measured shift, hit/miss, fidelity before → after) → landing / closed line.
 */
export default function Chain({ chain, deckCode, compact = false }: { chain: ChainT; deckCode?: string; compact?: boolean }) {
  const { card, versions } = chain;
  const v0 = versions.find((v) => v.v === 0) ?? versions[0];
  const last = versions[versions.length - 1];
  const tone = card.status === "landed" ? "accent" : card.status === "closed" ? "muted" : "outline";
  return (
    <article className="border border-rule p-3 flex flex-col gap-3">
      <header className="flex gap-3 items-start">
        {v0 && <CardFace elements={v0.elements} size="thumb" />}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge tone={tone}>{card.status}</Badge>
            {card.synthetic && <Badge tone="muted">synthetic</Badge>}
            <span className="text-xs text-muted">
              by {card.maker_nickname ?? "—"} · v {last?.v ?? 0}
              {card.max_edits ? ` of ${card.max_edits}` : ""}
            </span>
          </div>
          <div className="font-display text-lg mt-1 leading-tight">
            {card.title ? (
              <>
                {card.title}
                {card.title_by && <span className="text-[10px] text-muted ml-2 uppercase tracking-wider">{card.title_by === "k2" ? "named by K2" : card.title_by}</span>}
              </>
            ) : (
              <span className="text-muted">untitled</span>
            )}
          </div>
          {card.statement ? (
            <p className="text-sm mt-1">“{card.statement}”</p>
          ) : (
            <p className="text-xs text-muted mt-1">intent sealed until the card lands or closes</p>
          )}
          {v0 && (
            <div className="text-[11px] text-muted mt-1">
              v0 · {v0.elements.map((e) => `${e.label} (${e.slot})`).join(", ")} · F {fmt(v0.fidelity)} · n {v0.n_readings}
            </div>
          )}
        </div>
      </header>

      {versions.filter((v) => v.v > 0).length > 0 && (
        <ol className="flex flex-col gap-2 border-t border-rule pt-2">
          {versions
            .filter((v) => v.v > 0)
            .map((v) => {
              const e = v.edit;
              const eff = v.edit_effect;
              const bet = e ? AXES[e.bet_axis] : null;
              const prev = versions.find((p) => p.v === v.v - 1);
              return (
                <li key={v.version_id} className="text-sm flex gap-3">
                  {!compact && <CardFace elements={v.elements} size="thumb" highlight={e?.to_element_id ?? e?.element_id ?? null} />}
                  <div className="min-w-0 flex-1">
                    <div>
                      <span className="text-muted">v{v.v} · </span>
                      <span className="text-ink">{e?.editor_nickname ?? "someone"}</span> {e ? moveWords(e) : "edited"}
                    </div>
                    {bet && (
                      <div className="text-xs text-muted">
                        bet: <span className="text-ink">{bet[0]} ↔ {bet[1]}</span>
                        {eff && (
                          <>
                            {" "}
                            · shift {eff.delta === null ? "—" : `${eff.delta >= 0 ? "+" : ""}${eff.delta.toFixed(1)}`} ·{" "}
                            <span className={eff.hit ? "text-accent" : ""}>{eff.hit ? "hit +2" : "miss"}</span>
                            {eff.n_pairs !== undefined && <> · {eff.n_pairs} paired</>}
                          </>
                        )}
                      </div>
                    )}
                    {e?.rationale && <div className="text-xs mt-0.5 italic">“{e.rationale}”</div>}
                    <div className="text-[11px] text-muted mt-0.5">
                      F {fmt(prev?.fidelity)} → <span className={(v.fidelity ?? 0) > (prev?.fidelity ?? 0) ? "text-accent" : ""}>{fmt(v.fidelity)}</span> · n {v.n_readings}
                    </div>
                  </div>
                </li>
              );
            })}
        </ol>
      )}

      <footer className="text-xs border-t border-rule pt-2 flex items-center justify-between gap-2 flex-wrap">
        <span>
          {card.status === "landed" && chain.landing ? (
            <span className="text-accent">
              landed at v{last?.v ?? 0} · +{chain.landing.points_each} to {chain.landing.encoders.join(", ")}
            </span>
          ) : card.status === "closed" ? (
            <span className="text-muted">closed after {last?.v ?? 0} edit{(last?.v ?? 0) === 1 ? "" : "s"}</span>
          ) : card.status === "open" ? (
            <span>open for its next edit</span>
          ) : (
            <span className="text-muted">collecting readings</span>
          )}
        </span>
        {deckCode && (
          <Link href={`/decks/${deckCode}/cards/${card.id}`} className="underline underline-offset-2 text-muted">
            card page
          </Link>
        )}
      </footer>
    </article>
  );
}

function fmt(x: number | null | undefined) {
  return x === null || x === undefined ? "–" : x.toFixed(2);
}

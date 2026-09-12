"use client";
import CardFace from "@/components/CardFace";
import GapBars from "@/components/GapBars";
import GrammarStrip from "@/components/GrammarStrip";
import RevealPlot from "@/components/RevealPlot";
import VerdictBadge from "@/components/VerdictBadge";
import type { Reveal as RevealT, Room } from "@/lib/api";
import { AXES, axesToWords } from "@/lib/axes";
import { moveWords } from "@/lib/slots";
import { useNow } from "@/lib/useNow";

export default function Reveal({
  room,
  reveal,
  guestId,
  msUntil,
  onContinue,
  onReplay,
  busy,
}: {
  room: Room;
  reveal: RevealT;
  guestId: string | null;
  msUntil: (iso: string | null | undefined) => number;
  onContinue: () => void;
  onReplay: () => void;
  busy: boolean;
}) {
  useNow(500);
  const isHost = guestId !== null && room.host_id === guestId;
  const isHolder = guestId !== null && room.round?.holder_id === guestId;
  const rem = Math.max(0, msUntil(room.round?.phase_ends_at));
  const real = reveal.readings.filter((r) => !r.synthetic);
  const nSynth = reveal.readings.length - real.length;
  const v = reveal.version.v;
  const edit = reveal.version.edit;
  const eff = reveal.edit_effect;
  const ms = reveal.maker_score;
  const bet = eff ? AXES[eff.bet_axis] : edit ? AXES[edit.bet_axis] : null;
  const yourD = reveal.you?.d_total ?? null;

  return (
    <section className="flex flex-col gap-7 pt-3">
      <header className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-widest text-muted">
            card {room.round?.n_card ?? ""} · v{v} of {reveal.card.max_edits} · reveal{reveal.replay || room.round?.replay ? " · replay" : ""}
          </div>
          <h1 className="font-display text-2xl mt-1">{v === 0 ? "Did it get through?" : "What did the change do?"}</h1>
        </div>
        {room.round?.phase_ends_at && <div className="font-display text-2xl tabular-nums text-muted">{Math.ceil(rem / 1000)}s</div>}
      </header>

      {/* card + statement */}
      <div className="flex gap-4 items-start">
        <CardFace elements={reveal.version.elements} size="phone" highlight={reveal.edited_element_id} />
        <div className="text-sm min-w-0 flex-1">
          <div className="text-xs uppercase tracking-widest text-muted">{reveal.card.maker_nickname}&apos;s card</div>
          {reveal.card.statement ? (
            <p className="font-display text-lg leading-snug mt-1">“{reveal.card.statement}”</p>
          ) : (
            <p className="text-xs text-muted mt-1">The intent stays sealed until the card lands or closes — the next reader must not know it.</p>
          )}
          {edit && (
            <p className="text-sm mt-2">
              <span className="text-muted">v{v}:</span> {edit.editor_nickname ?? "the editor"} {moveWords(edit)}
              {edit.rationale && <span className="italic text-muted"> — “{edit.rationale}”</span>}
            </p>
          )}
          <div className="text-xs text-muted mt-2">
            fidelity F {fmt(reveal.fidelity)}
            {reveal.fidelity_prev !== null && reveal.fidelity_prev !== undefined && (
              <>
                {" "}
                (was {fmt(reveal.fidelity_prev)},{" "}
                <span className={(reveal.delta_fidelity ?? 0) > 0 ? "text-accent" : ""}>
                  ΔF {(reveal.delta_fidelity ?? 0) >= 0 ? "+" : ""}
                  {(reveal.delta_fidelity ?? 0).toFixed(2)}
                </span>
                )
              </>
            )}
          </div>
        </div>
      </div>

      {/* plot */}
      <div>
        <div className="flex items-baseline justify-between">
          <h2 className="font-display text-lg">Readings against the intent</h2>
          <span className="text-[11px] text-muted">
            ★ intent · <span className="text-accent">●</span> real · <span className="text-synth">●</span> synthetic{v > 0 && " · → shift"}
          </span>
        </div>
        <RevealPlot intentXy={reveal.intent_xy} readings={reveal.readings} radius={reveal.radius} youId={guestId} />
        <div className="text-[11px] text-muted mt-1">
          {reveal.pca_note}. Circle is illustrative: filled dots are inside r in eight dimensions, hollow are outside.
          {v > 0 && bet && (
            <>
              {" "}
              Arrows: each reader&apos;s move from v{v - 1} to v{v}; the bet was on <span className="text-ink">{bet[0]} ↔ {bet[1]}</span>.
            </>
          )}
        </div>
        {yourD !== null && (
          <div className="mt-2 border border-accent px-3 py-2 text-sm">
            Your distance from the intent: <span className="font-display text-xl text-accent">{yourD.toFixed(2)}</span>
            <span className="text-muted text-xs"> · r = {reveal.radius.toFixed(2)}</span>
            {reveal.you?.shift && <span className="text-muted text-xs"> · you moved {axesToWords(reveal.you.shift, 2)}</span>}
          </div>
        )}
      </div>

      {/* gaps */}
      <div className="border-t border-rule pt-4">
        <h2 className="font-display text-lg">Where the room missed</h2>
        <p className="text-xs text-muted mb-2">|intent − mean reading| per scale, largest first.</p>
        <GapBars gaps={reveal.gaps_abs} betAxis={eff?.bet_axis ?? edit?.bet_axis ?? null} signed={reveal.gaps_signed ?? null} />
      </div>

      {/* scorecard */}
      <div className="border-t border-rule pt-4 flex flex-col gap-3">
        {v === 0 && ms && (
          <div className="flex items-baseline gap-4">
            <div>
              <div className="text-xs uppercase tracking-widest text-muted">maker score</div>
              <div className="font-display text-5xl leading-none mt-1">
                {ms.points === null ? "–" : ms.points}
                <span className="text-lg text-muted"> pt</span>
              </div>
            </div>
            <div className="text-sm text-muted">
              {ms.n < ms.needs ? (
                <>needs {ms.needs} readers (had {ms.n})</>
              ) : (
                <>
                  {Math.round((ms.f ?? 0) * 100)}% of {ms.n} readers inside r.
                  <br />
                  Some got it, not all = 3 · nearly all = 1 · almost none = 0.
                </>
              )}
            </div>
          </div>
        )}
        {v > 0 && eff && bet && (
          <div className="flex items-baseline gap-4">
            <div>
              <div className="text-xs uppercase tracking-widest text-muted">the bet</div>
              <div className={`font-display text-4xl leading-none mt-1 ${eff.hit ? "text-accent" : ""}`}>{eff.hit ? "hit" : "miss"}</div>
            </div>
            <div className="text-sm">
              Bet: <span className="text-ink">{bet[0]} ↔ {bet[1]}</span> · shift{" "}
              <span className="tabular-nums">{eff.delta === null ? "no pairs" : `${eff.delta >= 0 ? "+" : ""}${eff.delta.toFixed(1)}`}</span>
              {eff.gap_before !== null && (
                <span className="text-muted">
                  {" "}
                  vs gap {eff.gap_before >= 0 ? "+" : ""}
                  {eff.gap_before.toFixed(1)}
                </span>
              )}
              {eff.hit && <span className="text-accent"> · +2</span>}
              <div className="text-xs text-muted">
                {eff.n_pairs} reader{eff.n_pairs === 1 ? "" : "s"} read both versions. A hit needs the same sign as the gap and |shift| ≥ 0.5.
              </div>
            </div>
          </div>
        )}
        {reveal.landing && reveal.landing.landed && (
          <div className="border border-accent px-3 py-2 text-sm">
            <span className="font-display text-lg text-accent">Landed.</span> F {fmt(reveal.fidelity)} ≥ {reveal.landing.threshold.toFixed(2)} ·{" "}
            +{reveal.landing.points_each} each to {reveal.landing.encoders.join(", ")}.
          </div>
        )}
        {!reveal.card.landed && reveal.card.status === "closed" && (
          <div className="text-sm text-muted">Closed after {reveal.card.max_edits} edits without landing. The chain stays in the deck.</div>
        )}
      </div>

      {/* readings, submission order */}
      <div>
        <h2 className="font-display text-lg">What the room received</h2>
        <ul className="mt-2 flex flex-col gap-2">
          {real.map((r, i) => (
            <li key={`${r.reader_id}-${i}`} className="border-b border-rule pb-2">
              <div className="flex justify-between text-sm">
                <span>
                  {r.nickname}
                  {r.reader_id === guestId && <span className="text-muted"> (you)</span>}
                </span>
                <span className="text-muted text-xs">d {r.d_total.toFixed(2)}</span>
              </div>
              <div className="text-xs text-muted">{axesToWords(r.axes)}</div>
              {r.free_text && <div className="text-sm mt-0.5">“{r.free_text}”</div>}
            </li>
          ))}
          {real.length === 0 && <li className="text-sm text-muted">No readings arrived.</li>}
        </ul>
        {nSynth > 0 && <div className="text-[11px] text-synth mt-2">+ {nSynth} synthetic seed readings on this version (muted in the plot)</div>}
      </div>

      {/* verdict */}
      <div className="border-t border-rule pt-4">
        <h2 className="font-display text-lg">Polysemy verdict for this version</h2>
        <p className="text-xs text-muted mb-2">Axes only; silhouette tested against a null. Needs eight readings.</p>
        <VerdictBadge verdict={reveal.verdict} />
      </div>

      {/* grammar strip */}
      <div className="border-t border-rule pt-4">
        <h2 className="font-display text-lg">The grammar, updated</h2>
        <p className="text-xs text-muted mb-3">What each symbol on this card carries in this deck, before and after this read. Watch the band move.</p>
        <GrammarStrip before={reveal.grammar_strip_before} after={reveal.grammar_strip} editedId={reveal.edited_element_id} />
      </div>

      <div className="flex flex-col gap-2 sticky bottom-3">
        {(isHost || isHolder) && (
          <button onClick={onContinue} disabled={busy} className="w-full bg-ink text-paper py-3 text-base tracking-wide">
            {reveal.card.status === "landed" || reveal.card.status === "closed" ? "Next card" : "Pass the card to the editor"}
          </button>
        )}
        {isHost && (
          <button onClick={onReplay} disabled={busy} className="w-full border border-ink py-2 text-sm">
            Replay a finished card
          </button>
        )}
        {!isHost && !isHolder && <p className="text-xs text-muted text-center">The relay continues when the clock runs out or the host continues.</p>}
      </div>
    </section>
  );
}

function fmt(x: number | null | undefined) {
  return x === null || x === undefined ? "–" : x.toFixed(2);
}

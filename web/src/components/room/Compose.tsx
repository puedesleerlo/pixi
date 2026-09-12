"use client";
import { useMemo, useRef, useState } from "react";
import CardFace from "@/components/CardFace";
import Dots from "@/components/Dots";
import ElementPicker from "@/components/ElementPicker";
import type { Axes, Element, LibraryGroup, Slot } from "@/lib/api";
import { autoAssign, capacity } from "@/lib/slots";
import { useNow } from "@/lib/useNow";

/**
 * Compose (the Maker's turn), as three guided steps:
 *   1. say what the card means (private)      2. mark it on the eight scales (the target)
 *   3. pick 2–5 symbols (the card the readers see)
 * A sticky footer tracks the three steps and holds the submit button, so the Maker always knows
 * what is still missing. Used by the room (timed) and by deck mode (untimed).
 */
export default function Compose({
  groups,
  groupsError,
  onSubmit,
  endsAt,
  msUntil,
  title = "Make a card that says one thing.",
  subtitle,
  submitLabel = "Seal it and send to the readers",
}: {
  groups: LibraryGroup[] | null;
  groupsError?: string | null;
  onSubmit: (body: { statement: string; axes: Axes; elements: { element_id: string; slot: Slot }[] }) => Promise<void>;
  endsAt?: string | null;
  msUntil?: (iso: string | null | undefined) => number;
  title?: string;
  subtitle?: string;
  submitLabel?: string;
}) {
  const [statement, setStatement] = useState("");
  const [axes, setAxes] = useState<(number | null)[]>(Array(8).fill(null));
  const [picks, setPicks] = useState<Element[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showHow, setShowHow] = useState(true);
  const stepRefs = [useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null), useRef<HTMLDivElement>(null)];
  useNow(250);
  const remaining = endsAt && msUntil ? Math.max(0, msUntil(endsAt)) : null;
  const expired = remaining !== null && remaining <= 0;

  const placed = useMemo(() => autoAssign(picks), [picks]);
  const cap = capacity(picks);
  const scalesDone = axes.filter((v) => v !== null).length;
  const step1 = statement.trim().length > 0;
  const step2 = scalesDone === 8;
  const step3 = picks.length >= 2 && placed.length === picks.length;
  const complete = step1 && step2 && step3;
  const nextStep = !step1 ? 0 : !step2 ? 1 : !step3 ? 2 : -1;
  const hasLarge = picks.some((p) => p.size_class === "large");

  function toggle(el: Element) {
    setErr(null);
    setPicks((p) => {
      if (p.some((x) => x.id === el.id)) return p.filter((x) => x.id !== el.id);
      if (capacity(p) <= 0 && !(el.size_class === "large" && !p.some((x) => x.size_class === "large"))) return p;
      return [...p, el];
    });
  }

  function goTo(i: number) {
    stepRefs[i].current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function submit() {
    if (!complete) {
      if (nextStep >= 0) goTo(nextStep);
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await onSubmit({
        statement: statement.trim().slice(0, 140),
        axes: axes.map((v) => v ?? 0),
        elements: placed.map((e) => ({ element_id: e.element_id, slot: e.slot })),
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const stepLabel = (done: boolean, n: number, text: string) => (
    <button type="button" onClick={() => goTo(n - 1)} className={`flex items-center gap-1.5 ${done ? "text-ink" : nextStep === n - 1 ? "text-accent" : "text-muted"}`}>
      <span className={`inline-flex items-center justify-center w-5 h-5 rounded-full border text-[11px] ${done ? "bg-ink text-paper border-ink" : "border-current"}`}>{done ? "✓" : n}</span>
      <span className="text-xs">{text}</span>
    </button>
  );

  return (
    <section className="flex flex-col gap-7 pt-4 pb-28">
      <header className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-widest text-muted">your turn · you are the maker</div>
          <h1 className="font-display text-2xl mt-1">{title}</h1>
          {subtitle && <p className="text-sm text-muted mt-1">{subtitle}</p>}
        </div>
        {remaining !== null && <div className={`font-display text-3xl tabular-nums ${remaining <= 15000 ? "text-accent" : ""}`}>{Math.ceil(remaining / 1000)}s</div>}
      </header>

      {showHow && (
        <div className="border border-rule bg-[#faf6ee] px-3 py-3 text-sm leading-relaxed">
          <div className="flex items-start justify-between gap-3">
            <div className="font-display text-base">How your turn works</div>
            <button type="button" onClick={() => setShowHow(false)} className="text-xs text-muted underline underline-offset-2">
              hide
            </button>
          </div>
          <ol className="mt-1.5 list-decimal pl-5 flex flex-col gap-1">
            <li>
              <b>Decide what your card means</b> and write it in one sentence. Nobody else sees this.
            </li>
            <li>
              <b>Mark that meaning on eight scales.</b> This is the target: each reader&apos;s answer will be measured as a distance from it.
            </li>
            <li>
              <b>Build the card from symbols</b> (2–5). The readers see only the card, then tap the same eight scales.
            </li>
          </ol>
          <p className="mt-2 text-muted text-xs">
            You score <b>3</b> if some readers land on your meaning but not all, <b>1</b> if everyone does, <b>0</b> if nobody. Then the next player changes one symbol and bets on what it will do.
          </p>
        </div>
      )}

      {/* step 1 */}
      <div ref={stepRefs[0]} className="flex flex-col gap-2 scroll-mt-4">
        <div className="flex items-baseline justify-between">
          <div className="text-xs uppercase tracking-widest text-muted">step 1 · what does your card mean?</div>
          {step1 && <span className="text-[11px] text-muted">done</span>}
        </div>
        <textarea
          value={statement}
          onChange={(e) => setStatement(e.target.value.slice(0, 140))}
          maxLength={140}
          rows={2}
          placeholder="One sentence. Readers never see it."
          className="w-full border border-ink px-3 py-2 text-base"
          disabled={expired}
        />
        <div className="flex justify-between text-[11px] text-muted">
          <span>e.g. “letting go of something, gently, and being renewed by it”</span>
          <span>{statement.length}/140</span>
        </div>
      </div>

      {/* step 2 */}
      <div ref={stepRefs[1]} className="flex flex-col gap-2 scroll-mt-4">
        <div className="flex items-baseline justify-between">
          <div className="text-xs uppercase tracking-widest text-muted">step 2 · where does that meaning sit?</div>
          <span className={`text-[11px] ${step2 ? "text-muted" : "text-accent"}`}>{scalesDone}/8</span>
        </div>
        <p className="text-xs text-muted">Tap one dot per row. The middle dot means “neither”. Readers will tap the same rows without seeing yours.</p>
        <Dots values={axes} onChange={(i, v) => setAxes((a) => a.map((x, j) => (j === i ? v : x)))} disabled={expired} />
      </div>

      {/* step 3 */}
      <div ref={stepRefs[2]} className="flex flex-col gap-3 scroll-mt-4">
        <div className="flex items-baseline justify-between">
          <div className="text-xs uppercase tracking-widest text-muted">step 3 · build the card</div>
          <span className={`text-[11px] ${step3 ? "text-muted" : "text-accent"}`}>{picks.length}/5 symbols{picks.length < 2 ? " · need 2" : ""}</span>
        </div>
        <div className="flex gap-4 items-start">
          <CardFace elements={placed} size="phone" emptySlots showSalience />
          <div className="text-xs leading-relaxed flex flex-col gap-2">
            <p>Tap symbols below to place them. Tap again to remove.</p>
            <p className="text-muted">
              The <b className="text-ink">center</b> is the loudest slot, the sides the quietest — a symbol&apos;s weight in the grammar is its slot.
            </p>
            <p className="text-muted">
              {hasLarge ? "The first large symbol took the center." : "A large symbol (whole figure) fills the center. Without one the center stays empty."}
              {cap <= 0 && picks.length > 0 ? " The card is full." : ""}
            </p>
            {picks.length > 0 && (
              <button type="button" onClick={() => setPicks([])} className="self-start underline underline-offset-2 text-muted">
                start over
              </button>
            )}
          </div>
        </div>
        {groupsError && <p className="text-sm text-accent">Could not load the library: {groupsError}</p>}
        {groups ? (
          <ElementPicker
            groups={groups}
            selected={picks.map((p) => p.id)}
            onToggle={toggle}
            disableAll={expired}
            disabledIds={
              cap <= 0
                ? new Set(groups.flatMap((g) => g.elements.filter((e) => !(e.size_class === "large" && !hasLarge)).map((e) => e.id)))
                : new Set()
            }
          />
        ) : (
          !groupsError && <p className="text-sm text-muted">Loading the symbols…</p>
        )}
      </div>

      {err && <p className="text-sm text-accent">{err}</p>}

      {/* sticky footer: progress + submit */}
      <div className="fixed left-0 right-0 bottom-0 bg-paper/95 backdrop-blur border-t border-rule px-4 pt-2 pb-3 z-20">
        <div className="max-w-md mx-auto flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            {stepLabel(step1, 1, "meaning")}
            {stepLabel(step2, 2, `scales ${scalesDone}/8`)}
            {stepLabel(step3, 3, `symbols ${picks.length}`)}
          </div>
          <button
            onClick={submit}
            disabled={busy || expired}
            className={`w-full py-3 text-base tracking-wide sticky ${complete ? "bg-ink text-paper" : "border border-ink text-ink"}`}
          >
            {expired ? "Time's up" : busy ? "Sealing…" : complete ? submitLabel : nextStep === 0 ? "Next: write what the card means" : nextStep === 1 ? `Next: mark the scales (${scalesDone}/8)` : "Next: pick at least 2 symbols"}
          </button>
        </div>
      </div>
    </section>
  );
}

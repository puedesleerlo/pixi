"use client";
import { useMemo, useState } from "react";
import CardFace from "@/components/CardFace";
import ElementPicker from "@/components/ElementPicker";
import IntentPanel from "@/components/room/IntentPanel";
import type { Element, IntentView, LibraryGroup, PlacedElement, Slot } from "@/lib/api";
import { AXES } from "@/lib/axes";
import { applyMove, freeSlots, mayOccupy, Move, MoveType } from "@/lib/slots";
import { useNow } from "@/lib/useNow";

const TYPES: { t: MoveType; label: string; hint: string }[] = [
  { t: "add", label: "add", hint: "put a symbol in a free slot" },
  { t: "remove", label: "remove", hint: "take a symbol off the card" },
  { t: "swap", label: "swap", hint: "replace a symbol, same slot" },
  { t: "move", label: "move", hint: "change a symbol's slot" },
];

/**
 * Edit: the intent (private), the card, exactly ONE move with a live preview, a bet on one axis,
 * an optional rationale. Used by the room (timed) and by deck mode (untimed).
 */
export default function Edit({
  elements,
  intent,
  groups,
  groupsError,
  byId,
  endsAt,
  msUntil,
  v,
  maxEdits,
  onSubmit,
  rationaleRequired = false,
}: {
  elements: PlacedElement[];
  intent: IntentView | null;
  groups: LibraryGroup[] | null;
  groupsError?: string | null;
  byId: Map<string, Element>;
  endsAt?: string | null;
  msUntil?: (iso: string | null | undefined) => number;
  v: number;
  maxEdits: number;
  onSubmit: (body: { type: MoveType; element_id: string; to_element_id?: string; to_slot?: Slot; bet_axis: number; rationale?: string }) => Promise<void>;
  rationaleRequired?: boolean;
}) {
  const [type, setType] = useState<MoveType | null>(null);
  const [onCard, setOnCard] = useState<string | null>(null); // element on the card (remove/swap/move)
  const [pick, setPick] = useState<string | null>(null); // element from the picker (add/swap)
  const [toSlot, setToSlot] = useState<Slot | null>(null);
  const [bet, setBet] = useState<number | null>(null);
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useNow(250);
  const remaining = endsAt && msUntil ? Math.max(0, msUntil(endsAt)) : null;
  const expired = remaining !== null && remaining <= 0;

  const lookup = (id: string) => {
    const e = byId.get(id);
    return e ? { id: e.id, label: e.label, image_url: e.image_url, size_class: e.size_class, origin: e.origin, caption: e.caption } : undefined;
  };

  const move: Move | null = useMemo(() => {
    if (!type) return null;
    if (type === "add") return pick ? { type, element_id: pick, to_slot: toSlot ?? undefined } : null;
    if (type === "remove") return onCard ? { type, element_id: onCard } : null;
    if (type === "swap") return onCard && pick ? { type, element_id: onCard, to_element_id: pick } : null;
    return onCard && toSlot ? { type, element_id: onCard, to_slot: toSlot } : null;
  }, [type, pick, onCard, toSlot]);

  const preview = useMemo(() => {
    if (!move) return { elements, error: null as string | null };
    try {
      return { elements: applyMove(elements, move, lookup), error: null as string | null };
    } catch (e) {
      return { elements, error: e instanceof Error ? e.message : String(e) };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [move, elements, byId]);

  const onCardIds = new Set(elements.map((e) => e.element_id));
  const free = freeSlots(elements);
  const complete = !!move && !preview.error && bet !== null && (!rationaleRequired || rationale.trim().length > 0);

  function chooseType(t: MoveType) {
    setType(t);
    setOnCard(null);
    setPick(null);
    setToSlot(null);
    setErr(null);
  }

  async function submit() {
    if (!complete || !move || bet === null) return;
    setBusy(true);
    setErr(null);
    try {
      await onSubmit({ ...move, bet_axis: bet, rationale: rationale.trim() ? rationale.trim().slice(0, 140) : undefined });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  const changed = move && !preview.error ? (move.type === "swap" ? move.to_element_id ?? null : move.element_id) : null;

  return (
    <section className="flex flex-col gap-5 pt-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-widest text-muted">
            you hold the card · edit {v + 1} of {maxEdits}
          </div>
          <h1 className="font-display text-2xl mt-1">One change. One bet.</h1>
          <p className="text-sm text-muted mt-1">Talk it over out loud if you like; what enters the record is your one move and what you predict it does.</p>
        </div>
        {remaining !== null && <div className={`font-display text-3xl tabular-nums ${remaining <= 10000 ? "text-accent" : ""}`}>{Math.ceil(remaining / 1000)}s</div>}
      </header>

      {intent ? <IntentPanel intent={intent} /> : <p className="text-xs text-muted">Loading the intent…</p>}

      <div className="flex gap-4 items-start">
        <div className="flex flex-col items-center gap-1">
          <CardFace
            elements={preview.elements}
            size="phone"
            highlight={changed}
            selectable={type === "add" || type === "move" ? "slots" : type ? "elements" : null}
            selected={type === "move" && toSlot ? toSlot : onCard}
            emptySlots={type === "add" || type === "move"}
            onSelect={(id) => {
              if (type === "move" || type === "swap" || type === "remove") {
                setOnCard(id);
                setToSlot(null);
              }
            }}
            onSelectSlot={(s) => {
              if (type === "add" || type === "move") setToSlot(s);
            }}
          />
          <div className="text-[10px] text-muted">{move && !preview.error ? "preview" : "current card"}</div>
        </div>
        <div className="flex-1 flex flex-col gap-2">
          <div className="text-xs uppercase tracking-widest text-muted">the move</div>
          <div className="grid grid-cols-2 gap-1.5">
            {TYPES.map(({ t, label, hint }) => (
              <button key={t} type="button" onClick={() => chooseType(t)} disabled={expired} className={`text-left border px-2 py-1.5 ${type === t ? "border-ink bg-ink text-paper" : "border-rule"}`}>
                <div className="text-sm">{label}</div>
                <div className={`text-[10px] ${type === t ? "text-paper/80" : "text-muted"}`}>{hint}</div>
              </button>
            ))}
          </div>
          <div className="text-[11px] text-muted leading-relaxed">
            {type === "add" && (pick ? `adding ${byId.get(pick)?.label ?? pick}${toSlot ? ` to ${toSlot}` : " (auto slot, or tap a free slot)"}` : "pick a symbol below" + (free.length ? "" : " — the card is full"))}
            {type === "remove" && (onCard ? `removing ${elements.find((e) => e.element_id === onCard)?.label}` : "tap a symbol on the card")}
            {type === "swap" && (onCard ? (pick ? `swapping ${elements.find((e) => e.element_id === onCard)?.label} for ${byId.get(pick)?.label ?? pick}` : "now pick the replacement below") : "tap the symbol to replace")}
            {type === "move" && (onCard ? (toSlot ? `moving ${elements.find((e) => e.element_id === onCard)?.label} to ${toSlot}` : "now tap a free slot") : "tap a symbol on the card")}
            {!type && "choose add, remove, swap or move"}
          </div>
          {preview.error && <div className="text-xs text-accent">{preview.error}</div>}
          {(type === "add" || type === "move") && free.length > 0 && (
            <div className="flex flex-wrap gap-1 text-[11px]">
              {free.map((s) => {
                const size = type === "add" ? byId.get(pick ?? "")?.size_class : elements.find((e) => e.element_id === onCard)?.size_class;
                const ok = !size || mayOccupy(size, s);
                return (
                  <button key={s} type="button" disabled={!ok || expired} onClick={() => setToSlot(s)} className={`border px-2 py-0.5 ${toSlot === s ? "border-ink bg-ink text-paper" : "border-rule"}`}>
                    {s}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {(type === "add" || (type === "swap" && onCard)) && (
        <div>
          <div className="text-xs uppercase tracking-widest text-muted mb-2">{type === "add" ? "symbol to add" : "replacement"}</div>
          {groupsError && <p className="text-sm text-accent">Could not load the library: {groupsError}</p>}
          {groups ? (
            <ElementPicker
              groups={groups}
              selected={pick ? [pick] : []}
              onToggle={(el) => setPick((p) => (p === el.id ? null : el.id))}
              disabledIds={new Set([...onCardIds, ...(type === "swap" ? groups.flatMap((g) => g.elements.filter((e) => !mayOccupy(e.size_class, elements.find((x) => x.element_id === onCard)?.slot ?? "top")).map((e) => e.id)) : [])])}
              disableAll={expired}
              single
            />
          ) : (
            !groupsError && <p className="text-sm text-muted">Loading the library…</p>
          )}
        </div>
      )}

      <div className="border-t border-rule pt-3">
        <div className="text-xs uppercase tracking-widest text-muted mb-2">the bet · which scale moves the most toward the intent?</div>
        <div className="grid grid-cols-2 gap-1.5">
          {AXES.map(([l, r], i) => (
            <button key={i} type="button" onClick={() => setBet(i)} disabled={expired} className={`border px-2 py-1.5 text-xs text-left ${bet === i ? "border-accent bg-accent text-paper" : "border-rule"}`}>
              {l} ↔ {r}
            </button>
          ))}
        </div>
      </div>

      <div>
        <div className="text-xs uppercase tracking-widest text-muted mb-1">rationale{rationaleRequired ? "" : " · optional"}</div>
        <input value={rationale} onChange={(e) => setRationale(e.target.value.slice(0, 140))} maxLength={140} placeholder="Why this change?" className="w-full border border-rule px-3 py-2 text-base" disabled={expired} />
        <div className="text-[11px] text-muted text-right">{rationale.length}/140</div>
      </div>

      {err && <p className="text-sm text-accent">{err}</p>}
      <button onClick={submit} disabled={!complete || busy || expired} className="w-full bg-ink text-paper py-3 text-base tracking-wide sticky bottom-3">
        {expired ? "Time's up" : busy ? "Sending…" : complete ? "Make the change and send to the readers" : !move ? "Choose one move" : preview.error ? "That move is not allowed" : bet === null ? "Place your bet" : "Add a rationale"}
      </button>
    </section>
  );
}

// Slots and the auto-assignment / one-move rules, mirrored from the server (contract §2).
import type { PlacedElement, SizeClass, Slot } from "./api";

export const SLOTS: Record<Slot, number> = { center: 1.0, top: 0.7, bottom: 0.7, left: 0.5, right: 0.5 };
export const SLOT_ORDER: Slot[] = ["center", "top", "bottom", "left", "right"];
export const FILL_ORDER: Slot[] = ["top", "bottom", "left", "right"];

export interface Pickable {
  id: string;
  label: string;
  image_url: string | null;
  size_class?: SizeClass | null;
  origin?: PlacedElement["origin"];
  caption?: string;
}

export function mayOccupy(size: SizeClass | null | undefined, slot: Slot): boolean {
  return slot !== "center" || size === "large";
}

/**
 * Pick order preserved: the first `large` element takes center; the rest fill
 * top, bottom, left, right. No large → center stays empty (max 4).
 * Returns null for an element that does not fit (overflow).
 */
export function autoAssign(picks: Pickable[]): PlacedElement[] {
  const firstLarge = picks.find((p) => p.size_class === "large");
  const out: PlacedElement[] = [];
  if (firstLarge) out.push(toPlaced(firstLarge, "center"));
  let k = 0;
  for (const p of picks) {
    if (firstLarge && p.id === firstLarge.id) continue;
    if (k >= FILL_ORDER.length) break;
    out.push(toPlaced(p, FILL_ORDER[k++]));
  }
  return out;
}

/** How many more elements can be picked given the current picks. */
export function capacity(picks: Pickable[]): number {
  const hasLarge = picks.some((p) => p.size_class === "large");
  return (hasLarge ? 5 : 4) - picks.length;
}

export function toPlaced(p: Pickable, slot: Slot): PlacedElement {
  return {
    element_id: p.id,
    slot,
    label: p.label,
    image_url: p.image_url,
    origin: p.origin,
    size_class: p.size_class ?? null,
    caption: p.caption,
  };
}

export type MoveType = "add" | "remove" | "swap" | "move";

export interface Move {
  type: MoveType;
  element_id: string;
  to_element_id?: string;
  to_slot?: Slot;
}

export function freeSlots(elements: PlacedElement[]): Slot[] {
  const used = new Set(elements.map((e) => e.slot));
  return SLOT_ORDER.filter((s) => !used.has(s));
}

/** Apply one move for the live preview; throws a human message when illegal (mirrors the server). */
export function applyMove(elements: PlacedElement[], move: Move, lookup: (id: string) => Pickable | undefined): PlacedElement[] {
  const cur = elements.map((e) => ({ ...e }));
  const on = cur.find((e) => e.element_id === move.element_id);
  switch (move.type) {
    case "add": {
      if (on) throw new Error("that element is already on the card");
      if (cur.length >= 5) throw new Error("the card is full");
      const el = lookup(move.element_id);
      if (!el) throw new Error("unknown element");
      const free = freeSlots(cur).filter((s) => mayOccupy(el.size_class, s));
      const slot = move.to_slot ?? free[0];
      if (!slot || !free.includes(slot)) throw new Error(el.size_class === "small" ? "no free slot (small symbols cannot take the center)" : "no free slot");
      cur.push(toPlaced(el, slot));
      return cur;
    }
    case "remove": {
      if (!on) throw new Error("that element is not on the card");
      if (cur.length <= 2) throw new Error("a card keeps at least two elements");
      return cur.filter((e) => e.element_id !== move.element_id);
    }
    case "swap": {
      if (!on) throw new Error("that element is not on the card");
      if (!move.to_element_id) throw new Error("pick a replacement");
      if (cur.some((e) => e.element_id === move.to_element_id)) throw new Error("the replacement is already on the card");
      const el = lookup(move.to_element_id);
      if (!el) throw new Error("unknown element");
      if (!mayOccupy(el.size_class, on.slot)) throw new Error("a small symbol cannot take the center");
      return cur.map((e) => (e.element_id === move.element_id ? toPlaced(el, on.slot) : e));
    }
    case "move": {
      if (!on) throw new Error("that element is not on the card");
      if (!move.to_slot) throw new Error("pick a slot");
      if (!freeSlots(cur).includes(move.to_slot)) throw new Error("that slot is taken");
      if (!mayOccupy(on.size_class, move.to_slot)) throw new Error("a small symbol cannot take the center");
      return cur.map((e) => (e.element_id === move.element_id ? { ...e, slot: move.to_slot! } : e));
    }
  }
}

/** "swapped Crown for Wheel", "added Star to top" … */
export function moveWords(m: { type: MoveType; element_label?: string; element_id: string; to_element_label?: string | null; to_element_id?: string | null; to_slot?: Slot | null }): string {
  const a = m.element_label ?? m.element_id;
  const b = m.to_element_label ?? m.to_element_id ?? "";
  switch (m.type) {
    case "add":
      return `added ${a}${m.to_slot ? ` to ${m.to_slot}` : ""}`;
    case "remove":
      return `removed ${a}`;
    case "swap":
      return `swapped ${a} for ${b}`;
    case "move":
      return `moved ${a} to ${m.to_slot ?? "another slot"}`;
  }
}

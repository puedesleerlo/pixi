"use client";
import type { PlacedElement, Slot } from "@/lib/api";
import { imageSrc } from "@/lib/api";
import { SLOTS } from "@/lib/slots";

/**
 * The card renderer (contract §2): a paper frame at 3:5 with five fixed slot boxes.
 * Each box holds an <img> (a crop) or a text tile when the element has no image.
 * Nothing on the face reveals an element's origin. `highlight` outlines ONE slot
 * (the edited element on the Reveal screen — never during a read).
 */
const BOX: Record<Slot, { left: number; top: number; width: number; height: number }> = {
  top: { left: 30, top: 4, width: 40, height: 20 },
  center: { left: 24, top: 27, width: 52, height: 46 },
  bottom: { left: 30, top: 76, width: 40, height: 20 },
  left: { left: 1, top: 38, width: 22, height: 24 },
  right: { left: 77, top: 38, width: 22, height: 24 },
};

export default function CardFace({
  elements,
  size = "phone",
  highlight = null,
  selectable = null,
  selected = null,
  onSelect,
  onSelectSlot,
  emptySlots = false,
  className = "",
  showSalience = false,
}: {
  elements: PlacedElement[];
  size?: "phone" | "big" | "thumb";
  highlight?: string | null;
  /** when set, elements (and free slots if `emptySlots`) become tappable */
  selectable?: "elements" | "slots" | null;
  selected?: string | Slot | null;
  onSelect?: (element_id: string) => void;
  onSelectSlot?: (slot: Slot) => void;
  emptySlots?: boolean;
  className?: string;
  showSalience?: boolean;
}) {
  const width = size === "big" ? "min(88vw, 360px)" : size === "thumb" ? "72px" : "min(62vw, 240px)";
  const bySlot = new Map<Slot, PlacedElement>(elements.map((e) => [e.slot, e]));
  const slots = Object.keys(BOX) as Slot[];
  const tiny = size === "thumb";
  return (
    <div
      className={`relative bg-[#faf6ee] border border-ink select-none ${className}`}
      style={{ width, aspectRatio: "3 / 5" }}
      role="img"
      aria-label={elements.length ? `card with ${elements.map((e) => e.label).join(", ")}` : "empty card"}
    >
      {/* inner hairline frame */}
      <div className="absolute inset-[3%] border border-rule pointer-events-none" />
      {slots.map((slot) => {
        const b = BOX[slot];
        const el = bySlot.get(slot);
        const isHi = !!el && highlight === el.element_id;
        const isSel = el ? selected === el.element_id : selected === slot;
        const tappable = el ? selectable === "elements" : selectable === "slots" && emptySlots;
        const style: React.CSSProperties = {
          left: `${b.left}%`,
          top: `${b.top}%`,
          width: `${b.width}%`,
          height: `${b.height}%`,
        };
        const src = el ? imageSrc(el.image_url) : null;
        const inner = el ? (
          src ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={src} alt={el.label} className="w-full h-full object-contain" draggable={false} loading="eager" />
          ) : (
            <Tile label={el.label} tiny={tiny} />
          )
        ) : emptySlots ? (
          <div className="w-full h-full border border-dashed border-rule flex items-center justify-center text-[10px] text-muted">
            {tiny ? "" : slot}
          </div>
        ) : null;
        const outline = isHi ? "outline outline-2 outline-accent outline-offset-2" : isSel ? "outline outline-2 outline-ink outline-offset-2" : "";
        const cls = `absolute flex items-center justify-center ${outline} ${tappable ? "cursor-pointer" : ""}`;
        return tappable ? (
          <button
            key={slot}
            type="button"
            className={cls}
            style={style}
            onClick={() => (el ? onSelect?.(el.element_id) : onSelectSlot?.(slot))}
            aria-label={el ? `${el.label} in ${slot}` : `empty ${slot} slot`}
          >
            {inner}
            {showSalience && !tiny && <Sal slot={slot} />}
          </button>
        ) : (
          <div key={slot} className={cls} style={style}>
            {inner}
            {showSalience && !tiny && el && <Sal slot={slot} />}
          </div>
        );
      })}
    </div>
  );
}

function Tile({ label, tiny }: { label: string; tiny: boolean }) {
  return (
    <div className="w-full h-full bg-[#ece5d6] border border-ink/70 flex items-center justify-center p-[6%] text-center">
      <span
        className="font-display text-ink leading-tight"
        style={{ fontVariant: "small-caps", fontSize: tiny ? 6 : "clamp(9px, 2.6vw, 14px)" }}
      >
        {label}
      </span>
    </div>
  );
}

function Sal({ slot }: { slot: Slot }) {
  return (
    <span className="absolute -bottom-3 right-0 text-[9px] font-mono text-muted bg-paper px-0.5">{SLOTS[slot].toFixed(1)}</span>
  );
}

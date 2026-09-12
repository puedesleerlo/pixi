"use client";
import { imageSrc } from "@/lib/api";
import type { Version } from "@/lib/types";

/**
 * A card version as an image (spec: every version is an image). Synthetic playground cards have no image:
 * they render as a paper face listing their symbols, so the relay still works on seeded decks.
 */
export default function CardImage({
  imageUrl,
  symbols,
  names,
  size = "big",
  highlight,
  className = "",
}: {
  imageUrl: string | null | undefined;
  symbols?: Version["symbols_detected"] | null;
  names?: Record<string, string>;
  size?: "big" | "phone" | "thumb";
  highlight?: string | null;
  className?: string;
}) {
  const w = size === "big" ? "w-full max-w-[340px]" : size === "phone" ? "w-[150px]" : "w-[84px]";
  const src = imageSrc(imageUrl);
  if (src) {
    return (
      <div className={`${w} ${className}`}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt="" className="w-full h-auto border border-ink" draggable={false} />
      </div>
    );
  }
  const list = [...(symbols ?? [])].sort((a, b) => b.salience - a.salience);
  return (
    <div className={`${w} aspect-[11/19] border border-ink bg-[#faf6ee] p-2 flex flex-col gap-1 ${className}`}>
      <div className="text-[9px] uppercase tracking-widest text-muted">no image · symbols</div>
      {list.map((s) => (
        <div key={s.symbol_id} className={`text-xs border px-1 py-0.5 ${highlight === s.symbol_id ? "border-accent text-accent" : "border-rule"}`} style={{ fontVariant: "small-caps", opacity: 0.55 + 0.45 * s.salience }}>
          {names?.[s.symbol_id] ?? s.symbol_id}
        </div>
      ))}
      {list.length === 0 && <div className="text-xs text-muted">empty</div>}
    </div>
  );
}

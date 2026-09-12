"use client";
import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { imageSrc } from "@/lib/api";
import type { Region } from "@/lib/types";

/** Drag a rectangle on an image; returns a normalised bbox {x, y, w, h} in 0..1. */
export default function CropPicker({ imageUrl, value, onChange }: { imageUrl: string; value: Region | null; onChange: (r: Region | null) => void }) {
  const t = useTranslations("symbols");
  const ref = useRef<HTMLDivElement>(null);
  const [start, setStart] = useState<{ x: number; y: number } | null>(null);
  const [drag, setDrag] = useState<Region | null>(null);
  const norm = (e: React.PointerEvent) => {
    const r = ref.current!.getBoundingClientRect();
    return { x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)) };
  };
  const rect = (a: { x: number; y: number }, b: { x: number; y: number }): Region => ({ x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y) });
  const shown = drag ?? value;
  const src = imageSrc(imageUrl) ?? imageUrl;
  return (
    <div className="flex flex-col gap-1">
      <div
        ref={ref}
        className="relative select-none touch-none w-full max-w-[280px] cursor-crosshair"
        onPointerDown={(e) => {
          (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
          const p = norm(e);
          setStart(p);
          setDrag({ x: p.x, y: p.y, w: 0, h: 0 });
        }}
        onPointerMove={(e) => {
          if (start) setDrag(rect(start, norm(e)));
        }}
        onPointerUp={(e) => {
          if (start) {
            const r = rect(start, norm(e));
            setStart(null);
            setDrag(null);
            onChange(r.w > 0.02 && r.h > 0.02 ? r : null);
          }
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt="" className="w-full block pointer-events-none" draggable={false} />
        {shown && shown.w > 0 && (
          <div className="absolute border-2 border-accent bg-accent/10 pointer-events-none" style={{ left: `${shown.x * 100}%`, top: `${shown.y * 100}%`, width: `${shown.w * 100}%`, height: `${shown.h * 100}%` }} />
        )}
      </div>
      <div className="text-[11px] text-muted">
        {value ? `bbox ${value.x.toFixed(2)}, ${value.y.toFixed(2)}, ${value.w.toFixed(2)}, ${value.h.toFixed(2)}` : t("dragRectangle")}
        {value && (
          <button type="button" className="ml-2 underline" onClick={() => onChange(null)}>
            {t("clearCrop")}
          </button>
        )}
      </div>
    </div>
  );
}

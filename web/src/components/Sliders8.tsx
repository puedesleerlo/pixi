"use client";
import { AXES } from "@/lib/axes";
import type { Axes8 } from "@/lib/types";

/** Eight bipolar sliders −3..+3 (declared meaning / intent). */
export default function Sliders8({ value, onChange, disabled = false }: { value: Axes8; onChange: (v: Axes8) => void; disabled?: boolean }) {
  return (
    <div className="flex flex-col gap-2">
      {AXES.map(([l, r], i) => (
        <label key={i} className="flex items-center gap-2 text-xs">
          <span className="w-20 text-right text-muted">{l}</span>
          <input
            type="range"
            min={-3}
            max={3}
            step={1}
            value={value[i] ?? 0}
            disabled={disabled}
            onChange={(e) => onChange(value.map((x, j) => (j === i ? Number(e.target.value) : x)))}
            className="flex-1 accent-[#c8361e]"
            aria-label={`${l} to ${r}`}
          />
          <span className="w-20 text-muted">{r}</span>
          <span className="w-6 tabular-nums text-right">{value[i] > 0 ? `+${value[i]}` : value[i]}</span>
        </label>
      ))}
    </div>
  );
}

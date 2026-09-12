"use client";
import { useState } from "react";
import type { Element, LibraryGroup } from "@/lib/api";
import { imageSrc } from "@/lib/api";

/**
 * The symbol picker: elements grouped by library with thumbnail (or tile), label, caption and
 * size badge. Origin is shown here (never on the card face).
 */
export default function ElementPicker({
  groups,
  selected,
  onToggle,
  disabledIds = new Set(),
  disableAll = false,
  single = false,
}: {
  groups: LibraryGroup[];
  selected: string[];
  onToggle: (el: Element) => void;
  disabledIds?: Set<string>;
  disableAll?: boolean;
  single?: boolean;
}) {
  const [filter, setFilter] = useState<string>("all");
  const [size, setSize] = useState<"all" | "large" | "small">("all");
  const shown = groups.filter((g) => filter === "all" || g.id === filter);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2 text-xs">
        {groups.length > 1 && (
          <>
            <Chip on={filter === "all"} onClick={() => setFilter("all")}>
              all libraries
            </Chip>
            {groups.map((g) => (
              <Chip key={g.id} on={filter === g.id} onClick={() => setFilter(g.id)}>
                {g.name}
              </Chip>
            ))}
            <span className="w-2" />
          </>
        )}
        <Chip on={size === "all"} onClick={() => setSize("all")}>
          any size
        </Chip>
        <Chip on={size === "large"} onClick={() => setSize("large")}>
          large (center)
        </Chip>
        <Chip on={size === "small"} onClick={() => setSize("small")}>
          small
        </Chip>
      </div>
      {shown.map((g) => (
        <div key={g.id}>
          <div className="text-xs uppercase tracking-widest text-muted mb-1">{g.name}</div>
          <ul className="grid grid-cols-3 sm:grid-cols-4 gap-2">
            {g.elements
              .filter((e) => size === "all" || e.size_class === size)
              .map((e) => {
                const on = selected.includes(e.id);
                const dis = disableAll || (disabledIds.has(e.id) && !on);
                const src = imageSrc(e.image_url);
                return (
                  <li key={e.id}>
                    <button
                      type="button"
                      disabled={dis && !on}
                      onClick={() => onToggle(e)}
                      aria-pressed={on}
                      className={`w-full text-left border p-1.5 flex flex-col gap-1 ${on ? "border-accent outline outline-1 outline-accent" : "border-rule"} ${dis && !on ? "opacity-40" : ""}`}
                    >
                      <div className="w-full aspect-square bg-[#faf6ee] border border-rule flex items-center justify-center overflow-hidden">
                        {src ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={src} alt={e.label} className="w-full h-full object-contain" loading="lazy" draggable={false} />
                        ) : (
                          <span className="font-display text-[11px] text-center px-1" style={{ fontVariant: "small-caps" }}>
                            {e.label}
                          </span>
                        )}
                      </div>
                      <div className="text-xs leading-tight">
                        <span className="text-ink">{e.label}</span>
                        <span className={`ml-1 text-[9px] uppercase tracking-wider ${e.size_class === "large" ? "text-ink" : "text-muted"}`}>{e.size_class}</span>
                      </div>
                      <div className="text-[9px] leading-tight text-muted line-clamp-2">
                        {e.origin === "generated" ? (
                          <span className="border border-dashed border-ink px-0.5">generated · no attestation</span>
                        ) : e.origin === "tile" ? (
                          <>tile · {e.caption ?? "no crop yet"}</>
                        ) : (
                          e.caption ?? e.gloss ?? ""
                        )}
                      </div>
                    </button>
                  </li>
                );
              })}
          </ul>
        </div>
      ))}
      {single && <p className="text-[11px] text-muted">Pick one.</p>}
    </div>
  );
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} className={`px-2 py-1 border ${on ? "border-ink bg-ink text-paper" : "border-rule text-muted"}`}>
      {children}
    </button>
  );
}

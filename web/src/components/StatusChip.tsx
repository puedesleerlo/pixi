import type { CardStatus, Coherence } from "@/lib/types";

const TONE: Record<string, string> = {
  draft: "border-rule text-muted",
  reading: "border-ink text-ink",
  open: "border-accent text-accent",
  landed: "bg-ink text-paper border-ink",
  closed: "border-rule text-muted line-through",
  archived: "border-rule text-muted",
  legible: "border-ink text-ink",
  polysemous: "border-accent text-accent",
  noisy: "border-rule text-muted",
  collecting: "border-rule text-muted",
  consistent: "border-ink text-ink",
  contested: "border-accent text-accent",
  untested: "border-rule text-muted",
  ready: "border-ink text-ink",
  partial: "border-rule text-muted",
  planned: "border-rule text-muted",
};

export default function StatusChip({ value, label, className = "" }: { value: CardStatus | Coherence | string; label?: string; className?: string }) {
  return <span className={`inline-block border px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${TONE[value] ?? "border-rule text-muted"} ${className}`}>{label ?? value}</span>;
}

import Link from "next/link";
import StatusChip from "@/components/StatusChip";
import { imageSrc } from "@/lib/api";
import type { Card, StructurePosition } from "@/lib/types";

export default function CardTile({ deckSlug, card, position }: { deckSlug: string; card: Card; position?: StructurePosition | null }) {
  const src = imageSrc(card.current_version?.thumb_url ?? card.current_version?.image_url);
  return (
    <Link href={`/d/${deckSlug}/cards/${card.id}`} className="border border-rule hover:border-ink bg-[#faf6ee] flex flex-col">
      <div className="aspect-[11/19] bg-[#efe9dc] overflow-hidden flex items-center justify-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {src ? <img src={src} alt={card.title ?? position?.title ?? card.position_key} className="w-full h-full object-cover" loading="lazy" /> : <span className="text-[10px] text-muted px-2 text-center">{card.status}</span>}
      </div>
      <div className="p-1.5 text-[11px] flex flex-col gap-0.5">
        <div className="flex justify-between gap-1">
          <span className="truncate">{position?.title ?? card.title ?? card.position_key}</span>
          {card.branches?.length > 1 && <span title="branches">⑂</span>}
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          <StatusChip value={card.status} />
          {card.verdict?.verdict && <StatusChip value={card.verdict.verdict} />}
          {typeof card.fidelity === "number" && <span className="text-muted">F {card.fidelity.toFixed(2)}</span>}
          {typeof card.editors_count === "number" && card.editors_count > 0 && <span className="text-muted">✎{card.editors_count}</span>}
        </div>
      </div>
    </Link>
  );
}

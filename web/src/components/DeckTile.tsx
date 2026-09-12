import Link from "next/link";
import type { Deck } from "@/lib/types";
import { imageSrc } from "@/lib/api";

export default function DeckTile({ deck, chips = [] }: { deck: Deck; chips?: string[] }) {
  const src = imageSrc(deck.cover_url);
  return (
    <Link href={`/d/${deck.slug}`} className="border border-rule hover:border-ink flex flex-col bg-[#faf6ee]">
      <div className="aspect-[3/2] bg-[#efe9dc] flex items-center justify-center overflow-hidden">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {src ? <img src={src} alt="" className="w-full h-full object-cover" /> : <span className="font-display text-3xl text-muted">{deck.name.slice(0, 1)}</span>}
      </div>
      <div className="p-2 flex flex-col gap-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-display text-base truncate">{deck.name}</span>
          <span className="text-[10px] uppercase tracking-wider text-muted">{deck.visibility}</span>
        </div>
        {deck.origin?.kind === "fork" && <span className="text-[10px] text-muted">fork · {deck.lineage?.ancestors?.[0]?.name ?? deck.origin.forked_from_deck_id}</span>}
        {deck.origin?.kind === "base" && <span className="text-[10px] text-muted">from {deck.origin.base_deck_id}</span>}
        <div className="flex flex-wrap gap-1">
          {chips.map((c) => (
            <span key={c} className="text-[10px] border border-rule px-1">
              {c}
            </span>
          ))}
        </div>
      </div>
    </Link>
  );
}

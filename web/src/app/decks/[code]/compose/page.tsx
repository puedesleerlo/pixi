"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import Compose from "@/components/room/Compose";
import { api, getGuestId } from "@/lib/api";
import { useDeckElements } from "@/lib/useDeckElements";

/** Deck mode (T2): compose a card with no timer; readers arrive by link. */
export default function DeckComposePage() {
  const params = useParams<{ code: string }>();
  const router = useRouter();
  const code = (params?.code ?? "PLAY").toString().toUpperCase();
  const { groups, error } = useDeckElements(code);
  const [guest, setGuest] = useState<string | null>(null);
  const [anyone, setAnyone] = useState(true);
  useEffect(() => setGuest(getGuestId()), []);
  return (
    <section className="pt-4 flex flex-col gap-3">
      <div className="text-xs uppercase tracking-widest text-muted">
        <Link href={`/decks/${code}`} className="underline underline-offset-2">
          deck {code}
        </Link>{" "}
        · compose (no timer)
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={anyone} onChange={(e) => setAnyone(e.target.checked)} />
        anyone in the deck may edit this card <span className="text-xs text-muted">(recommended; you can narrow it on the card page)</span>
      </label>
      <Compose
        groups={groups}
        groupsError={error}
        title="Compose a card for the deck."
        subtitle="Readers arrive by link. Once enough have read it, an approved editor makes one change and bets on it."
        submitLabel="Seal and put it in the deck"
        onSubmit={async (b) => {
          const chain = await api.deckCompose(code, { guest_id: guest ?? "", ...b, approved_editors: anyone ? "*" : [] });
          router.push(`/decks/${code}/cards/${chain.card.id}`);
        }}
      />
    </section>
  );
}

"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import Chain from "@/components/Chain";
import { api, Chain as ChainT, deckCodeOf, Room } from "@/lib/api";

/** The room's chains, fetched card by card from the deck, and scores per player in join order. */
export default function Ended({ room }: { room: Room }) {
  const deck = deckCodeOf(room);
  const ids = [...new Set(room.history.filter((h) => h.card_id && !h.replay).map((h) => h.card_id))];
  const [chains, setChains] = useState<Record<string, ChainT>>({});
  useEffect(() => {
    let alive = true;
    for (const id of ids) {
      api
        .deckCard(deck, id)
        .then((c) => alive && setChains((m) => ({ ...m, [id]: c })))
        .catch(() => {});
    }
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deck, ids.join(",")]);
  return (
    <section className="flex flex-col gap-6 pt-6">
      <header>
        <div className="text-xs uppercase tracking-widest text-muted">room {room.code} · relay over</div>
        <h1 className="font-display text-2xl mt-1">Everyone has been Maker.</h1>
        <p className="text-sm text-muted mt-1">What the deck keeps is not what each card means, but every edit, bet and measured shift on the way.</p>
      </header>
      <div>
        <div className="text-xs uppercase tracking-widest text-muted mb-1">points · join order</div>
        <ul className="border-t border-rule">
          {room.players.map((p) => (
            <li key={p.guest_id} className="flex justify-between border-b border-rule py-2 text-sm">
              <span>{p.nickname}</span>
              <span className="tabular-nums">{room.scores[p.guest_id] ?? 0}</span>
            </li>
          ))}
        </ul>
        <p className="text-[11px] text-muted mt-1">Room scores die with the room.</p>
      </div>
      <div className="flex flex-col gap-3">
        {ids.map((id) => (chains[id] ? <Chain key={id} chain={chains[id]} deckCode={deck} /> : <div key={id} className="text-sm text-muted">loading {id}…</div>))}
        {ids.length === 0 && <p className="text-sm text-muted">No cards were finished.</p>}
      </div>
      <p className="text-sm">
        <Link href={`/decks/${deck}`} className="underline underline-offset-2">
          See the whole deck
        </Link>{" "}
        ·{" "}
        <Link href={`/decks/${deck}/grammar`} className="underline underline-offset-2">
          the grammar
        </Link>{" "}
        ·{" "}
        <Link href="/" className="underline underline-offset-2">
          new room
        </Link>
      </p>
    </section>
  );
}

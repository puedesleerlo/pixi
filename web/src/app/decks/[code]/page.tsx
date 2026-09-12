"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Chain from "@/components/Chain";
import { api, CardStatus, DeckHome, getGuestId, getNickname, setGuestId, setNickname } from "@/lib/api";

const ORDER: { s: CardStatus; label: string; hint: string }[] = [
  { s: "open", label: "open for edit", hint: "enough readings are in; any approved editor may make the next move" },
  { s: "reading", label: "collecting readings", hint: "waiting for readers before the next edit opens" },
  { s: "landed", label: "landed", hint: "the room read it the way the Maker meant" },
  { s: "closed", label: "closed", hint: "edit budget spent without landing — the chain is kept" },
];

export default function DeckHomePage() {
  const params = useParams<{ code: string }>();
  const code = (params?.code ?? "PLAY").toString().toUpperCase();
  const [home, setHome] = useState<DeckHome | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [guest, setGuest] = useState<string | null>(null);
  const [joinBusy, setJoinBusy] = useState(false);
  const [showSynthetic, setShowSynthetic] = useState(false);

  const load = useCallback(() => {
    api
      .deckHome(code)
      .then(setHome)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [code]);
  useEffect(() => {
    setGuest(getGuestId());
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  async function join() {
    setJoinBusy(true);
    try {
      const nick = getNickname() || prompt("Nickname?") || "anon";
      const d = await api.joinDeck(code, getGuestId(), nick);
      setNickname(nick);
      const me = d.members?.find((m) => m.nickname === nick);
      if (me && !getGuestId()) {
        setGuestId(me.guest_id);
        setGuest(me.guest_id);
      }
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setJoinBusy(false);
    }
  }

  if (err && !home) return <Empty title="Deck unavailable" body={err} />;
  if (!home) return <Empty title="Loading the deck…" body="" />;
  const { deck, cards } = home;
  const isMember = guest !== null && deck.members?.some((m) => m.guest_id === guest);
  const total = ORDER.reduce((n, o) => n + (cards[o.s]?.length ?? 0), 0);
  const visible = (s: CardStatus) => (cards[s] ?? []).filter((c) => showSynthetic || !c.card.synthetic);
  const nSynth = ORDER.reduce((n, o) => n + (cards[o.s] ?? []).filter((c) => c.card.synthetic).length, 0);

  return (
    <section className="pt-6 flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <div className="text-xs uppercase tracking-widest text-muted">deck · code {deck.code}</div>
        <h1 className="font-display text-3xl">{deck.name}</h1>
        <p className="text-sm text-muted">
          Libraries: {deck.libraries?.join(", ") || "—"} · {deck.members?.length ?? deck.n_members ?? 0} members · {total} cards · max {deck.max_edits ?? 3} edits ·{" "}
          {deck.ready_threshold ?? 3} readings open an edit
        </p>
        <div className="flex flex-wrap gap-2 text-sm">
          <Link href={`/decks/${code}/grammar`} className="border border-ink px-3 py-1.5">
            Grammar
          </Link>
          <Link href={`/decks/${code}/read`} className="border border-ink px-3 py-1.5">
            Read a card
          </Link>
          {isMember ? (
            <Link href={`/decks/${code}/compose`} className="border border-ink px-3 py-1.5">
              Compose a card
            </Link>
          ) : (
            <button onClick={join} disabled={joinBusy} className="border border-ink px-3 py-1.5">
              {joinBusy ? "Joining…" : "Join this deck"}
            </button>
          )}
          <Link href="/" className="border border-rule px-3 py-1.5 text-muted">
            Start a room
          </Link>
        </div>
        {deck.members?.length > 0 && (
          <p className="text-[11px] text-muted">members · {deck.members.map((m) => m.nickname).join(" · ")}</p>
        )}
        {nSynth > 0 && (
          <label className="flex items-center gap-2 text-xs text-muted">
            <input type="checkbox" checked={showSynthetic} onChange={(e) => setShowSynthetic(e.target.checked)} />
            show {nSynth} synthetic seed cards
          </label>
        )}
      </header>

      {ORDER.map((o) => {
        const list = visible(o.s);
        if (!list.length) return null;
        return (
          <div key={o.s} className="flex flex-col gap-3">
            <div>
              <h2 className="font-display text-lg">
                {o.label} <span className="text-muted text-sm">· {list.length}</span>
              </h2>
              <p className="text-xs text-muted">{o.hint}</p>
            </div>
            {list.map((c) => (
              <Chain key={c.card.id} chain={c} deckCode={code} compact />
            ))}
          </div>
        );
      })}
      {total === 0 && <p className="text-sm text-muted">No cards yet. Start a room, or compose one here.</p>}
      {err && <p className="text-xs text-accent">{err}</p>}
    </section>
  );
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <section className="pt-10">
      <h1 className="font-display text-2xl">{title}</h1>
      <p className="text-sm text-muted mt-2">{body}</p>
    </section>
  );
}

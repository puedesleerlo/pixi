"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Compose from "@/components/room/Compose";
import Edit from "@/components/room/Edit";
import Ended from "@/components/room/Ended";
import Lobby from "@/components/room/Lobby";
import Read from "@/components/room/Read";
import Reveal from "@/components/room/Reveal";
import Waiting from "@/components/room/Waiting";
import { api, deckCodeOf, getGuestId, getNickname, Room, setGuestId, setNickname } from "@/lib/api";
import { useDeckElements } from "@/lib/useDeckElements";
import { useRoom } from "@/lib/useRoom";

export default function RoomPage() {
  const params = useParams<{ code: string }>();
  const code = (params?.code ?? "").toString().toUpperCase();
  const [guest, setGuest] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setGuest(getGuestId());
    setReady(true);
  }, []);
  const { room, setRoom, error, status, refresh, msUntil } = useRoom(code, ready);
  const deckCode = room ? deckCodeOf(room) : null;
  const { groups, byId, error: groupsError } = useDeckElements(deckCode);
  const [busy, setBusy] = useState(false);
  const [actionErr, setActionErr] = useState<string | null>(null);

  if (!ready) return null;
  if (!room) {
    if (status === 404) return <Empty title="No such room" body={`There is no room ${code}. Check the code or start a new one.`} />;
    if (error) return <Empty title="Connecting…" body={`Could not reach the server yet (${error}). Retrying.`} />;
    return <Empty title="Loading" body="" />;
  }

  const inRoom = guest !== null && room.players.some((p) => p.guest_id === guest);
  if (!inRoom && room.phase !== "ended") {
    return (
      <JoinInline
        room={room}
        onJoined={(gid, r) => {
          setGuestId(gid);
          setGuest(gid);
          setRoom(r);
        }}
      />
    );
  }

  const rnd = room.round;
  const isHolder = !!rnd && rnd.holder_id === guest;
  const isMaker = !!rnd && rnd.maker_id === guest;
  const isEditor = !!rnd && (rnd.editor_id ?? null) === guest && room.phase === "edit";
  const submitted = room.you?.submitted || (guest !== null && !!rnd?.submitted_reader_ids?.includes(guest));
  const holderNick = rnd?.holder_nickname ?? nick(room, rnd?.holder_id);

  async function act(fn: () => Promise<Room>) {
    setBusy(true);
    setActionErr(null);
    try {
      const r = await fn();
      setRoom(r);
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      refresh();
    }
  }

  let body: React.ReactNode;
  switch (room.phase) {
    case "lobby":
      body = <Lobby room={room} guestId={guest} busy={busy} onStart={() => act(() => api.startRoom(code, guest!))} />;
      break;
    case "compose":
      body = isMaker ? (
        <Compose
          groups={groups}
          groupsError={groupsError}
          endsAt={rnd?.phase_ends_at ?? null}
          msUntil={msUntil}
          onSubmit={async (b) => {
            const r = await api.compose(code, { guest_id: guest!, ...b });
            setRoom(r);
          }}
        />
      ) : (
        <Waiting room={room} msUntil={msUntil} title={`${nick(room, rnd?.maker_id)} is composing…`} body="The Maker is writing a private meaning and building a card from symbols. You will see only the card: tap what you receive on eight scales, sixty seconds." />
      );
      break;
    case "read":
      if (isHolder) {
        body = (
          <div>
            <Waiting room={room} msUntil={msUntil} title="Readers are reading your card." body="They see only the card and tap the eight scales. Next you will see how close each reader landed to your meaning, and your score. Then the card passes to the next player for one change." showCount showCard />
            {room.intent && (
              <div className="mt-6 max-w-sm mx-auto">
                <IntentPeek statement={room.intent.statement} />
              </div>
            )}
          </div>
        );
      } else if (!submitted && rnd?.version) {
        body = (
          <Read
            elements={rnd.version.elements}
            previousAxes={room.you?.previous_axes ?? null}
            endsAt={rnd.phase_ends_at}
            msUntil={msUntil}
            v={rnd.v}
            nCard={rnd.n_card}
            onSubmit={async (b) => {
              const r = await api.postReading(code, { guest_id: guest!, ...b });
              setRoom(r);
            }}
          />
        );
      } else {
        body = <Waiting room={room} msUntil={msUntil} title="Received — waiting for the others." body="The reveal opens when everyone has answered or the clock runs out." showCount />;
      }
      break;
    case "reveal":
      body = room.reveal ? (
        <Reveal
          room={room}
          reveal={room.reveal}
          guestId={guest}
          msUntil={msUntil}
          busy={busy}
          onContinue={() => act(() => api.continueRoom(code, guest!))}
          onReplay={() => act(() => api.replay(code, guest!))}
        />
      ) : (
        <Empty title="Computing the reveal…" body={room.reveal_error ?? ""} />
      );
      break;
    case "edit":
      body =
        isEditor && rnd?.version ? (
          <Edit
            elements={rnd.version.elements}
            intent={room.intent ?? null}
            groups={groups}
            groupsError={groupsError}
            byId={byId}
            endsAt={rnd.phase_ends_at}
            msUntil={msUntil}
            v={rnd.v}
            maxEdits={rnd.max_edits}
            onSubmit={async (b) => {
              const r = await api.edit(code, { guest_id: guest!, ...b });
              setRoom(r);
            }}
          />
        ) : (
          <Waiting room={room} msUntil={msUntil} title={`${rnd?.editor_nickname ?? nick(room, rnd?.editor_id)} is editing…`} body="One change and one bet. Then you read the card again — your previous answer will show as a ghost." showCard />
        );
      break;
    case "ended":
      body = <Ended room={room} />;
      break;
    default:
      body = <Empty title="Unknown phase" body={String(room.phase)} />;
  }

  return (
    <div>
      <div className="flex items-center justify-between text-[11px] text-muted pt-2 gap-2">
        <span>
          room <span className="tracking-widest text-ink">{room.code}</span> · {room.players.length} players
          {rnd && room.phase !== "lobby" && (
            <>
              {" "}
              · card {rnd.n_card} held by <span className="text-ink">{holderNick}</span>
            </>
          )}
        </span>
        <span className="truncate">
          {Object.keys(room.scores ?? {}).length > 0 && <>points · {room.players.map((p) => `${p.nickname} ${room.scores[p.guest_id] ?? 0}`).join(" · ")}</>}
        </span>
      </div>
      {actionErr && <p className="text-sm text-accent mt-2">{actionErr}</p>}
      {body}
    </div>
  );
}

function nick(room: Room, id: string | undefined | null) {
  return room.players.find((p) => p.guest_id === id)?.nickname ?? "someone";
}

function IntentPeek({ statement }: { statement: string }) {
  return (
    <div className="border border-ink p-3 text-sm">
      <div className="text-[10px] uppercase tracking-widest text-muted">your sealed intent</div>
      <p className="font-display text-lg leading-snug mt-1">“{statement}”</p>
    </div>
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

function JoinInline({ room, onJoined }: { room: Room; onJoined: (gid: string, r: Room) => void }) {
  const [nickname, setNick] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setNick(getNickname()), []);
  async function join() {
    if (!nickname.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await api.joinRoom(room.code, nickname.trim(), getGuestId());
      setNickname(nickname.trim());
      onJoined(res.guest_id, res.room);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }
  return (
    <section className="pt-10 flex flex-col gap-4 max-w-sm mx-auto">
      <div className="text-center">
        <div className="text-xs uppercase tracking-widest text-muted">join room</div>
        <div className="font-display text-6xl tracking-[0.18em] mt-1">{room.code}</div>
        <div className="text-xs text-muted mt-1">
          {room.players.length} in the room · {room.phase}
        </div>
      </div>
      <input value={nickname} onChange={(e) => setNick(e.target.value.slice(0, 24))} placeholder="Your nickname" className="w-full border border-ink px-3 py-3 text-base" autoFocus onKeyDown={(e) => e.key === "Enter" && join()} />
      {err && <p className="text-sm text-accent">{err}</p>}
      <button onClick={join} disabled={!nickname.trim() || busy} className="w-full bg-ink text-paper py-3 text-base tracking-wide">
        {busy ? "Joining…" : "Join as a Reader"}
      </button>
      <p className="text-xs text-muted text-center">Sixty seconds, eight taps. You report what you received; you are never scored.</p>
    </section>
  );
}

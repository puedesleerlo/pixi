"use client";
import CardFace from "@/components/CardFace";
import type { Room } from "@/lib/api";
import { useNow } from "@/lib/useNow";

/** Generic "someone else is doing something" screen with the server countdown. */
export default function Waiting({
  room,
  msUntil,
  title,
  body,
  showCount = false,
  showCard = false,
}: {
  room: Room;
  msUntil: (iso: string | null | undefined) => number;
  title: string;
  body: string;
  showCount?: boolean;
  showCard?: boolean;
}) {
  useNow(250);
  const rem = Math.max(0, msUntil(room.round?.phase_ends_at));
  const n = room.round?.n_readers ?? room.round?.reader_ids?.length ?? Math.max(0, room.players.length - 1);
  const k = room.round?.n_submitted ?? room.round?.submitted_reader_ids?.length ?? 0;
  return (
    <section className="pt-8 flex flex-col items-center text-center gap-3">
      <div className="text-xs uppercase tracking-widest text-muted">
        card {room.round?.n_card ?? "–"} · v{room.round?.v ?? 0}
      </div>
      <h1 className="font-display text-2xl">{title}</h1>
      <p className="text-sm text-muted max-w-sm">{body}</p>
      {showCard && room.round?.version && <CardFace elements={room.round.version.elements} size="phone" />}
      {room.round?.phase_ends_at && <div className="font-display text-5xl tabular-nums mt-1">{Math.ceil(rem / 1000)}s</div>}
      {showCount && (
        <div className="text-sm">
          {k}/{n} readings in
        </div>
      )}
    </section>
  );
}

"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Read from "@/components/room/Read";
import { api, ApiError, getGuestId, getNickname, ReadTask, setGuestId } from "@/lib/api";

/** Deck mode (T2): the read queue hands over the version with the fewest human readings. */
export default function DeckReadPage() {
  const params = useParams<{ code: string }>();
  const code = (params?.code ?? "PLAY").toString().toUpperCase();
  const [task, setTask] = useState<ReadTask | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "empty" | "done" | "error">("loading");
  const [err, setErr] = useState<string | null>(null);
  const [guest, setGuest] = useState<string | null>(null);

  const next = useCallback(() => {
    setState("loading");
    api
      .deckReadQueue(code, getGuestId())
      .then((t) => {
        const raw = t as unknown as { empty?: boolean; version?: ReadTask["version"] & { id?: string }; card?: { id: string }; card_id?: string; version_id?: string; v?: number; previous_axes?: number[] | null };
        if (raw.empty || !raw.version) {
          setState("empty");
          return;
        }
        const version = raw.version ?? (t as unknown as ReadTask["version"]);
        setTask({
          card_id: raw.card_id ?? raw.card?.id ?? "",
          version_id: raw.version_id ?? raw.version?.id ?? "",
          v: raw.v ?? version?.v ?? 0,
          version,
          previous_axes: raw.previous_axes ?? null,
        });
        setState("ready");
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) setState("empty");
        else {
          setErr(e instanceof Error ? e.message : String(e));
          setState("error");
        }
      });
  }, [code]);
  useEffect(() => {
    setGuest(getGuestId());
    next();
  }, [next]);

  return (
    <section className="pt-4 flex flex-col gap-4">
      <div className="text-xs uppercase tracking-widest text-muted">
        <Link href={`/decks/${code}`} className="underline underline-offset-2">
          deck {code}
        </Link>{" "}
        · read a card
      </div>
      {state === "loading" && <p className="text-sm text-muted">Finding a card that needs a reading…</p>}
      {state === "empty" && <p className="text-sm text-muted">Nothing to read right now — every open card has enough readings. Come back later.</p>}
      {state === "error" && <p className="text-sm text-accent">{err}</p>}
      {state === "done" && (
        <div className="flex flex-col gap-3">
          <p className="text-sm">Received. Thank you — you are never scored.</p>
          <button onClick={next} className="bg-ink text-paper py-3">
            Read another
          </button>
        </div>
      )}
      {state === "ready" && task?.version && (
        <Read
          key={task.version_id}
          elements={task.version.elements}
          previousAxes={task.previous_axes ?? null}
          endsAt={null}
          msUntil={() => 0}
          v={task.v}
          onSubmit={async (b) => {
            const res = (await api.deckReading(code, task.card_id, { guest_id: guest ?? "", version_id: task.version_id, ...b })) as unknown as { guest_id?: string };
            if (res?.guest_id && !guest) {
              setGuestId(res.guest_id);
              setGuest(res.guest_id);
            }
            setState("done");
          }}
        />
      )}
      {!getNickname() && state === "ready" && <p className="text-[11px] text-muted">Reading as a guest; readers need not be members.</p>}
    </section>
  );
}

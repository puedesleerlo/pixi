"use client";
import { useEffect, useState } from "react";
import QR from "@/components/QR";
import { apiUrl, type Room } from "@/lib/api";

export default function Lobby({ room, guestId, onStart, busy }: { room: Room; guestId: string | null; onStart: () => void; busy: boolean }) {
  const [joinUrl, setJoinUrl] = useState("");
  useEffect(() => {
    // Phones cannot reach "localhost": when the lobby is opened on the laptop itself, ask the API for
    // the machine's LAN address (or a configured public web URL) and put THAT in the QR code.
    const origin = window.location.origin;
    setJoinUrl(`${origin}/r/${room.code}`);
    const host = window.location.hostname;
    let cancelled = false;
    fetch(`${apiUrl()}/api/health`)
      .then((r) => r.json())
      .then((h: { lan_ip?: string | null; web_url?: string | null }) => {
        if (cancelled) return;
        if (h.web_url) setJoinUrl(`${h.web_url.replace(/\/$/, "")}/r/${room.code}`);
        else if ((host === "localhost" || host === "127.0.0.1") && h.lan_ip) {
          const u = new URL(origin);
          u.hostname = h.lan_ip;
          setJoinUrl(`${u.origin}/r/${room.code}`);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [room.code]);
  const isHost = guestId !== null && room.host_id === guestId;
  const canStart = isHost && room.players.length >= 2;
  const order = room.turn_order?.length ? room.turn_order : room.players.map((p) => p.guest_id);
  const nick = (id: string) => room.players.find((p) => p.guest_id === id)?.nickname ?? "?";

  return (
    <section className="flex flex-col items-center gap-6 pt-8">
      <div className="text-center">
        <div className="text-xs uppercase tracking-widest text-muted">room</div>
        <div className="font-display text-7xl tracking-[0.18em] leading-none mt-1">{room.code}</div>
        {joinUrl && <div className="text-xs text-muted mt-2 break-all">{joinUrl}</div>}
      </div>
      {joinUrl && <QR text={joinUrl} size={208} />}
      <div className="w-full max-w-sm">
        <div className="text-xs uppercase tracking-widest text-muted mb-2">turn order · {room.players.length} players</div>
        <ol className="border-t border-rule">
          {order.map((id, i) => (
            <li key={id} className="flex justify-between border-b border-rule py-2 text-sm">
              <span>
                <span className="text-muted tabular-nums mr-2">{i + 1}.</span>
                {nick(id)}
                {id === guestId && <span className="text-muted"> (you)</span>}
              </span>
              <span className="text-muted text-xs">{id === room.host_id ? "host" : ""}</span>
            </li>
          ))}
        </ol>
      </div>
      {isHost ? (
        <div className="w-full max-w-sm flex flex-col gap-2">
          <button onClick={onStart} disabled={!canStart || busy} className="w-full bg-ink text-paper py-3 text-base tracking-wide">
            {room.players.length < 2 ? "Start (need 2+ players)" : busy ? "Starting…" : "Start the relay"}
          </button>
          {room.players.length < 3 && <p className="text-xs text-muted text-center">3 or more players recommended: one holds the card, the rest read it.</p>}
        </div>
      ) : (
        <p className="text-sm text-muted">Waiting for the host to start.</p>
      )}
      <p className="text-xs text-muted text-center max-w-sm">
        The Maker composes a card from symbols and seals an intent. Everyone else reads it in eight taps. Then the card passes on: one change,
        one bet, one more read. Readers are never scored.
      </p>
    </section>
  );
}

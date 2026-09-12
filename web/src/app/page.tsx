"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, getGuestId, getNickname, setGuestId, setNickname } from "@/lib/api";

export default function JoinPage() {
  const router = useRouter();
  const [nickname, setNick] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState<"new" | "join" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setNick(getNickname()), []);

  async function create() {
    if (!nickname.trim()) return;
    setBusy("new");
    setErr(null);
    try {
      const res = await api.createRoom(nickname.trim(), getGuestId(), "PLAY");
      setGuestId(res.guest_id);
      setNickname(nickname.trim());
      router.push(`/r/${res.room.code}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  }
  async function join() {
    if (!nickname.trim() || code.length !== 4) return;
    setBusy("join");
    setErr(null);
    try {
      const res = await api.joinRoom(code, nickname.trim(), getGuestId());
      setGuestId(res.guest_id);
      setNickname(nickname.trim());
      router.push(`/r/${res.room.code}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  }

  return (
    <section className="pt-10 flex flex-col gap-8 max-w-sm mx-auto">
      <header>
        <h1 className="font-display text-5xl leading-none">PIXIE</h1>
        <p className="text-sm text-muted mt-3 leading-relaxed">
          A multiplayer relay on public-domain tarot symbols. One player composes a card and seals an intent; the others report what they
          received; then the card passes on — one change, one bet, one more read. Every edit is an experiment, and the experiments add up to
          a shared symbol grammar. Visual-communication research — nothing here predicts anything.
        </p>
      </header>

      <div className="flex flex-col gap-3">
        <label className="text-xs uppercase tracking-widest text-muted">nickname</label>
        <input value={nickname} onChange={(e) => setNick(e.target.value.slice(0, 24))} placeholder="e.g. ana" className="w-full border border-ink px-3 py-3 text-base" />
      </div>

      <div className="flex flex-col gap-3">
        <button onClick={create} disabled={!nickname.trim() || busy !== null} className="w-full bg-ink text-paper py-3 text-base tracking-wide">
          {busy === "new" ? "Creating…" : "New room"}
        </button>
        <div className="text-center text-xs text-muted">or</div>
        <div className="flex gap-2">
          <input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 4))}
            placeholder="CODE"
            inputMode="text"
            autoCapitalize="characters"
            className="flex-1 border border-ink px-3 py-3 text-base font-display tracking-[0.3em] uppercase"
            onKeyDown={(e) => e.key === "Enter" && join()}
          />
          <button onClick={join} disabled={!nickname.trim() || code.length !== 4 || busy !== null} className="border border-ink px-5 py-3 text-base">
            {busy === "join" ? "…" : "Join"}
          </button>
        </div>
      </div>
      {err && <p className="text-sm text-accent">{err}</p>}

      <p className="text-xs text-muted leading-relaxed">
        Rooms play in the <Link href="/decks/PLAY" className="underline underline-offset-2">Playground deck</Link> with the Smith 1909 library.
        Makers score on calibrated ambiguity (3 / 1 / 0), Editors score 2 when their bet lands, and everyone on a chain gets 1 when a card
        lands. Readers are never scored. The distance is a number you can recompute by hand; no model judges anything.
      </p>
    </section>
  );
}

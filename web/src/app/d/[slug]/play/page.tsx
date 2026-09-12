"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import Share from "@/components/Share";
import { useDeckCtx } from "@/components/ws/DeckContext";
import { getNickname, setNickname, v5 } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export default function PlayPage() {
  const t = useTranslations("playws");
  const router = useRouter();
  const { deck, me, atLeast } = useDeckCtx();
  const sessions = useLoad(() => v5.decks.sessions(deck.id).catch(() => []), [deck.id]);
  const [mode, setMode] = useState<"reading" | "relay">("relay");
  const [nick, setNick] = useState("");
  const [readTimer, setReadTimer] = useState(60);
  const [editTimer, setEditTimer] = useState(45);
  const [guests, setGuests] = useState(true);
  const [live, setLive] = useState(deck.settings?.live_generation_in_sessions ?? false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setNick(getNickname() || me?.name || ""), [me?.name]);

  async function host() {
    setBusy(true);
    setErr(null);
    try {
      setNickname(nick);
      const s = await v5.decks.createSession(deck.id, { mode, nickname: nick || undefined, settings: { read_timer: readTimer, edit_timer: editTimer, guests_allowed: guests, live_generation: live } });
      try {
        sessionStorage.setItem(`pixie_sid_${s.code}`, s.id);
      } catch {}
      router.push(`/s/${s.code}`);
    } catch (e) {
      setErr(`${t("sessionsSoon")} (${e instanceof Error ? e.message : e})`);
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      {atLeast("member") && (
        <section className="border border-rule p-4 flex flex-col gap-3 text-sm">
          <div className="font-display text-lg">{t("host")}</div>
          <div className="flex gap-2">
            {(["relay", "reading"] as const).map((m) => (
              <button key={m} type="button" onClick={() => setMode(m)} className={`border px-3 py-1 ${mode === m ? "border-ink bg-ink text-paper" : "border-rule"}`}>
                {t(`mode_${m}`)}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted">{mode === "relay" ? t("relayHint") : t("readingHint")}</p>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1 text-xs">
              <span className="uppercase tracking-widest text-muted">{t("nickname")}</span>
              <input value={nick} onChange={(e) => setNick(e.target.value.slice(0, 24))} className="border border-ink px-2 py-1.5 text-sm" />
            </label>
            <label className="flex flex-col gap-1 text-xs">
              <span className="uppercase tracking-widest text-muted">{t("readTimer")}</span>
              <input type="number" min={20} max={180} value={readTimer} onChange={(e) => setReadTimer(Number(e.target.value))} className="border border-rule px-2 py-1.5 text-sm" />
            </label>
            {mode === "relay" && (
              <label className="flex flex-col gap-1 text-xs">
                <span className="uppercase tracking-widest text-muted">{t("editTimer")}</span>
                <input type="number" min={20} max={180} value={editTimer} onChange={(e) => setEditTimer(Number(e.target.value))} className="border border-rule px-2 py-1.5 text-sm" />
              </label>
            )}
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={guests} onChange={(e) => setGuests(e.target.checked)} /> {t("guestsAllowed")}
            </label>
            {mode === "relay" && (
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} /> {t("liveGeneration")}
              </label>
            )}
          </div>
          <button type="button" disabled={busy} className="self-start bg-ink text-paper px-4 py-2" onClick={host}>
            {busy ? t("starting") : t("start")}
          </button>
          {err && <p className="text-xs text-accent">{err}</p>}
        </section>
      )}
      <section>
        <div className="font-display text-lg mb-1">{t("queue")}</div>
        <p className="text-xs text-muted mb-2">{t("queueHint")}</p>
        <Share path={`/d/${deck.slug}/read`} />
      </section>
      <section>
        <div className="font-display text-lg mb-1">{t("sessions")}</div>
        <ul className="text-sm flex flex-col gap-1">
          {sessions.data?.map((s) => (
            <li key={s.id}>
              <Link href={`/s/${s.code}`} className="underline">
                {s.code}
              </Link>{" "}
              · {t(`mode_${s.mode}`)} · {s.state} · {(s as { n_players?: number }).n_players ?? s.players?.length ?? 0} {t("players")}
            </li>
          ))}
          {sessions.data?.length === 0 && <li className="text-muted">{t("noSessions")}</li>}
        </ul>
      </section>
    </div>
  );
}

"use client";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import QR from "@/components/QR";
import { apiUrl } from "@/lib/api";
import type { SessionView } from "@/lib/types";

export default function Lobby({ view, onStart, busy }: { view: SessionView; onStart: () => void; busy: boolean }) {
  const t = useTranslations("session");
  const [joinUrl, setJoinUrl] = useState("");
  useEffect(() => {
    // Phones cannot reach "localhost": when the lobby is opened on the laptop, ask the API for the LAN address
    // (or the configured public web URL) and put THAT in the QR code.
    const origin = window.location.origin;
    setJoinUrl(`${origin}/s/${view.code}`);
    const host = window.location.hostname;
    let cancelled = false;
    fetch(`${apiUrl()}/api/health`)
      .then((r) => r.json())
      .then((h: { lan_ip?: string | null; web_url?: string | null }) => {
        if (cancelled) return;
        if (h.web_url) setJoinUrl(`${h.web_url.replace(/\/$/, "")}/s/${view.code}`);
        else if ((host === "localhost" || host === "127.0.0.1") && h.lan_ip) {
          const u = new URL(origin);
          u.hostname = h.lan_ip;
          setJoinUrl(`${u.origin}/s/${view.code}`);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [view.code]);
  const me = view.you.id;
  const canStart = view.you.is_host && view.players.length >= 2;
  const s = view.settings;
  return (
    <section className="flex flex-col items-center gap-6 pt-6">
      <div className="text-center">
        <div className="text-xs uppercase tracking-widest text-muted">{t("session")}</div>
        <div className="font-display text-7xl tracking-[0.18em] leading-none mt-1">{view.code}</div>
        {joinUrl && <div className="text-xs text-muted mt-2 break-all">{joinUrl}</div>}
      </div>
      {joinUrl && <QR text={joinUrl} size={208} />}
      <div className="w-full max-w-sm">
        <div className="text-xs uppercase tracking-widest text-muted mb-2">
          {t("players")} · {view.players.length}
        </div>
        <ol className="border-t border-rule">
          {view.players.map((p, i) => (
            <li key={p.user_or_guest_id} className="flex justify-between border-b border-rule py-2 text-sm">
              <span>
                <span className="text-muted tabular-nums mr-2">{i + 1}.</span>
                {p.nickname}
                {p.user_or_guest_id === me && <span className="text-muted"> ({t("you")})</span>}
              </span>
              <span className="text-muted text-xs">{p.user_or_guest_id === view.host_id ? t("host") : p.role === "reader" ? t("readerOnly") : t("player")}</span>
            </li>
          ))}
        </ol>
      </div>
      <div className="w-full max-w-sm text-xs text-muted border border-rule px-3 py-2">
        <div className="uppercase tracking-widest text-[10px] mb-1">{t("settings")}</div>
        <div>
          {view.mode === "relay" ? t("relay") : t("readingRounds")} · {t("read")} {s.read_timer}s · {t("edit")} {s.edit_timer}s · {t("maxEdits")} {s.max_edits}
        </div>
        <div>
          {t("guests")}: {s.guests_allowed ? t("yes") : t("no")} · {t("liveGeneration")}: {s.live_generation ? t("on") : t("off")}
        </div>
      </div>
      {view.you.is_host ? (
        <div className="w-full max-w-sm flex flex-col gap-2">
          <button onClick={onStart} disabled={!canStart || busy} className="w-full bg-ink text-paper py-3 text-base tracking-wide">
            {view.players.length < 2 ? t("startNeed") : busy ? t("starting") : t("start")}
          </button>
          {view.players.length < 4 && view.mode === "relay" && <p className="text-xs text-muted text-center">{t("fourRecommended")}</p>}
        </div>
      ) : (
        <p className="text-sm text-muted">{t("waitingHost")}</p>
      )}
      <p className="text-xs text-muted text-center max-w-sm">{view.mode === "relay" ? t("relayExplainer") : t("readingExplainer")}</p>
    </section>
  );
}

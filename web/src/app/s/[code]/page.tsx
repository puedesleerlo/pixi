"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import ErrorState from "@/components/ErrorState";
import ComposePick from "@/components/session/ComposePick";
import Editor from "@/components/session/Editor";
import Generating from "@/components/session/Generating";
import Holder from "@/components/session/Holder";
import Lobby from "@/components/session/Lobby";
import Reader from "@/components/session/Reader";
import Reveal from "@/components/session/Reveal";
import Summary from "@/components/session/Summary";
import Waiting from "@/components/session/Waiting";
import { ApiError, getNickname, setNickname, setToken, v5 } from "@/lib/api";
import type { Axes8, SessionReveal, SessionView } from "@/lib/types";
import { useSession } from "@/lib/useSession";

const SID_KEY = (code: string) => `pixie_sid_${code}`;

/**
 * /s/CODE — one page on `view.state`. Joining is idempotent (`POST /api/sessions/join` returns the view for a
 * returning player), so reloading a phone mid-round resumes where it was.
 */
export default function SessionPage() {
  const t = useTranslations("session");
  const params = useParams<{ code: string }>();
  const code = (params?.code ?? "").toString().toUpperCase();
  const [sid, setSid] = useState<string | null>(null);
  const [nick, setNick] = useState("");
  const [needNick, setNeedNick] = useState(false);
  const [joinErr, setJoinErr] = useState<string | null>(null);
  const [joinStatus, setJoinStatus] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [editNotice, setEditNotice] = useState<string | null>(null);
  const [pendingNote, setPendingNote] = useState<string | null>(null);
  const lastReveal = useRef<SessionReveal | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [deckSlug, setDeckSlug] = useState<string | null>(null);
  const { view, setView, error, status, refresh, msUntil } = useSession(sid);

  const join = useCallback(
    async (nickname: string) => {
      setJoinErr(null);
      try {
        let v: SessionView;
        try {
          v = await v5.sessions.join(code, nickname);
        } catch (e) {
          if (e instanceof ApiError && e.status === 401) {
            const g = await v5.auth.guest(nickname);
            if (g.token) setToken(g.token);
            v = await v5.sessions.join(code, nickname);
          } else throw e;
        }
        setNickname(nickname);
        try {
          sessionStorage.setItem(SID_KEY(code), v.id);
        } catch {}
        setSid(v.id);
        setView(v);
        setNeedNick(false);
      } catch (e) {
        setJoinErr(e instanceof Error ? e.message : String(e));
        setJoinStatus(e instanceof ApiError ? e.status : null);
        setNeedNick(true);
      }
    },
    [code, setView],
  );

  useEffect(() => {
    if (!code) return;
    const saved = getNickname();
    setNick(saved);
    let cached: string | null = null;
    try {
      cached = sessionStorage.getItem(SID_KEY(code));
    } catch {}
    if (cached) setSid(cached);
    if (saved) join(saved);
    else setNeedNick(true);
  }, [code, join]);

  // deck symbol names (for cards without images) and the deck slug (links out of the summary)
  useEffect(() => {
    if (!view?.deck_id) return;
    v5.symbols
      .list(view.deck_id, "active")
      .then((s) => setNames(Object.fromEntries(s.map((x) => [x.id, x.name]))))
      .catch(() => {});
    v5.decks
      .get(view.deck_id)
      .then((d) => setDeckSlug(d.slug ?? d.id))
      .catch(() => {});
  }, [view?.deck_id]);

  useEffect(() => {
    if (view?.reveal) lastReveal.current = view.reveal;
  }, [view?.reveal]);

  const act = useCallback(
    async (fn: () => Promise<SessionView>) => {
      setBusy(true);
      setActionErr(null);
      try {
        setView(await fn());
      } catch (e) {
        setActionErr(e instanceof Error ? e.message : String(e));
        refresh();
      } finally {
        setBusy(false);
      }
    },
    [setView, refresh],
  );

  // signed gaps for the editor: intent − mean of the last reveal's readings (the view carries the intent only)
  const gaps: Axes8 | null = useMemo(() => {
    const intent = view?.intent;
    const rv = lastReveal.current;
    if (!intent || !rv || rv.readings.length === 0) return null;
    const real = rv.readings.filter((r) => !r.synthetic);
    const rs = real.length ? real : rv.readings;
    return intent.axes.map((a, i) => a - rs.reduce((s, r) => s + r.axes[i], 0) / rs.length);
  }, [view?.intent, view?.reveal, view?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!code) return null;
  if (needNick && !view) {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (nick.trim()) join(nick.trim());
        }}
        className="max-w-md mx-auto px-4 py-10 flex flex-col gap-4"
      >
        <div className="text-xs uppercase tracking-widest text-muted">{t("session")}</div>
        <div className="font-display text-5xl tracking-[0.18em]">{code}</div>
        <p className="text-sm text-muted">{t("joinAsReader")}</p>
        <label className="text-xs uppercase tracking-widest text-muted">{t("nickname")}</label>
        <input value={nick} onChange={(e) => setNick(e.target.value.slice(0, 24))} className="border border-ink px-3 py-3 text-base" placeholder="e.g. ana" autoFocus />
        <button type="submit" disabled={!nick.trim()} className="bg-ink text-paper py-3 text-base tracking-wide">
          {t("join")}
        </button>
        {joinErr && <p className="text-sm text-accent">{joinStatus === 404 ? t("noSuchSession") : joinStatus === 403 ? t("guestsNotAllowed") : joinErr}</p>}
      </form>
    );
  }
  if (!view) {
    if (status === 404) return <ErrorState error={new Error(t("noSuchSession"))} status={404} />;
    return (
      <div className="max-w-md mx-auto px-4 py-10 text-sm text-muted">
        {error ? `${t("connecting")} (${error})` : t("loading")}
      </div>
    );
  }

  const me = view.you.id;
  const isHolder = !!me && view.round?.maker_or_editor_id === me;
  const nickOf = (id: string | null | undefined) => view.players.find((p) => p.user_or_guest_id === id)?.nickname ?? "?";
  let body: React.ReactNode;
  switch (view.state) {
    case "lobby":
      body = <Lobby view={view} busy={busy} onStart={() => act(() => v5.sessions.start(view.id))} />;
      break;
    case "compose": {
      const picker = view.mode === "relay" ? me === view.current_maker_id : view.you.is_host;
      body = picker ? (
        <ComposePick view={view} msUntil={msUntil} busy={busy} onChoose={(cid) => act(() => v5.sessions.choose(view.id, cid))} />
      ) : (
        <Waiting view={view} msUntil={msUntil} title={t("choosing", { name: view.mode === "relay" ? nickOf(view.current_maker_id) : nickOf(view.host_id) })} body={t("choosingBody")} />
      );
      break;
    }
    case "read": {
      if (view.you.role === "reader" && !view.you.submitted && view.round) {
        const rid = view.round.id;
        body = <Reader view={view} msUntil={msUntil} names={names} onSubmit={(b) => act(() => v5.sessions.submit(view.id, rid, b))} />;
      } else if (isHolder) {
        body = <Holder view={view} msUntil={msUntil} names={names} gaps={view.version && view.version.v > 0 ? gaps : null} />;
      } else {
        body = <Waiting view={view} msUntil={msUntil} title={view.you.submitted ? t("received") : t("readersReading")} body={t("readersReadingBody")} showCount showCard={!view.you.submitted && view.you.role !== "reader"} names={names} />;
      }
      break;
    }
    case "reveal":
      body = view.reveal ? (
        <Reveal view={view} reveal={view.reveal} msUntil={msUntil} names={names} busy={busy} onContinue={() => act(() => v5.sessions.advance(view.id))} />
      ) : (
        <Waiting view={view} msUntil={msUntil} title={t("revealing")} body={view.reveal_error ?? t("loading")} />
      );
      break;
    case "edit":
      body =
        me === view.current_editor_id ? (
          <Editor
            view={view}
            msUntil={msUntil}
            gaps={gaps}
            notice={editNotice}
            onSubmit={async (b) => {
              setEditNotice(null);
              try {
                const r = await v5.sessions.edit(view.id, b);
                setPendingNote(r.job?.status === "failed" ? `${t("jobFailed")} ${r.job.error ?? ""}` : null);
                setView(r.session);
              } catch (e) {
                if (e instanceof ApiError && e.status === 501) setEditNotice(t("liveEditsSoon"));
                else throw e;
              }
            }}
          />
        ) : (
          <Waiting view={view} msUntil={msUntil} title={t("editing", { name: nickOf(view.current_editor_id) })} body={t("editingBody")} showCard names={names} />
        );
      break;
    case "generating":
      body = <Generating view={view} msUntil={msUntil} names={names} busy={busy} pending={pendingNote} onSkip={() => act(() => v5.sessions.advance(view.id))} />;
      break;
    case "summary":
    case "ended":
      body = <Summary view={view} deckSlug={deckSlug} busy={busy} onEnd={() => act(() => (view.state === "summary" ? v5.sessions.advance(view.id) : v5.sessions.end(view.id)))} />;
      break;
    default:
      body = <Waiting view={view} msUntil={msUntil} title={view.state} body="" />;
  }

  return (
    <div className="max-w-md mx-auto px-4 pb-8">
      <div className="flex items-center justify-between text-[11px] text-muted pt-2">
        <span>
          {t("session")} <b className="tracking-widest">{view.code}</b> · {view.players.length} {t("players").toLowerCase()}
          {view.state !== "lobby" && Object.keys(view.scores ?? {}).length > 0 && (
            <>
              {" "}
              · {t("points")} {view.players.filter((p) => p.role !== "reader").map((p) => `${p.nickname} ${view.scores?.[p.user_or_guest_id] ?? 0}`).join(" · ")}
            </>
          )}
        </span>
        {view.you.is_host && view.state !== "ended" && view.state !== "lobby" && (
          <button onClick={() => act(() => v5.sessions.end(view.id))} className="underline underline-offset-2">
            {t("end")}
          </button>
        )}
      </div>
      {actionErr && <p className="text-xs text-accent mt-1">{actionErr}</p>}
      {body}
    </div>
  );
}

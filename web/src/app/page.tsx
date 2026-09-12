"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import DeckTile from "@/components/DeckTile";
import { v5 } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import type { Activity, Card, Deck } from "@/lib/types";

type Inbox = { to_read: Card[]; open_for_edit: Card[]; requests: Card[] };

/** Home — the dashboard (spec §4.2). Guests get the landing variant. */
export default function HomePage() {
  const t = useTranslations("home");
  const router = useRouter();
  const { data: me, signedIn, loading } = useMe();
  const [code, setCode] = useState("");
  const [decks, setDecks] = useState<Deck[] | null>(null);
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [activity, setActivity] = useState<Activity[] | null>(null);
  const [scanHint, setScanHint] = useState<string | null>(null);

  useEffect(() => {
    if (!signedIn) return;
    v5.auth.myDecks().then(setDecks).catch(() => setDecks([]));
    v5.auth.inbox().then(setInbox).catch(() => setInbox(null));
    v5.auth.myActivity().then(setActivity).catch(() => setActivity([]));
  }, [signedIn]);

  async function scan() {
    const w = window as unknown as { BarcodeDetector?: new (o: { formats: string[] }) => { detect: (s: ImageBitmapSource) => Promise<{ rawValue: string }[]> } };
    if (!w.BarcodeDetector || !navigator.mediaDevices?.getUserMedia) {
      setScanHint(t("scanUnsupported"));
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      const video = document.createElement("video");
      video.srcObject = stream;
      await video.play();
      const det = new w.BarcodeDetector({ formats: ["qr_code"] });
      const deadline = Date.now() + 20000;
      while (Date.now() < deadline) {
        const found = await det.detect(video).catch(() => []);
        if (found.length) {
          stream.getTracks().forEach((tr) => tr.stop());
          const m = found[0].rawValue.match(/\/(?:s|r)\/([A-Z]{4})/i);
          router.push(m ? `/s/${m[1].toUpperCase()}` : found[0].rawValue);
          return;
        }
        await new Promise((r) => setTimeout(r, 250));
      }
      stream.getTracks().forEach((tr) => tr.stop());
      setScanHint(t("scanTimeout"));
    } catch {
      setScanHint(t("scanUnsupported"));
    }
  }

  const join = (e: React.FormEvent) => {
    e.preventDefault();
    if (code.length === 4) router.push(`/play?code=${code}`);
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 flex flex-col gap-10">
      <section className="grid md:grid-cols-[1.2fr_1fr] gap-8 items-start [&>*]:min-w-0">
        <div>
          <h1 className="font-display text-4xl leading-tight">{t("headline")}</h1>
          <p className="text-muted mt-3 max-w-prose">{t("sub")}</p>
          {!signedIn && !loading && (
            <div className="flex gap-3 mt-5 text-sm">
              <Link href="/auth/sign-in" className="bg-ink text-paper px-4 py-2">
                {t("signIn")}
              </Link>
              <Link href="/explore" className="border border-ink px-4 py-2">
                {t("browseBase")}
              </Link>
            </div>
          )}
        </div>
        <form onSubmit={join} className="border border-ink p-4 flex flex-col gap-2 bg-[#faf6ee]">
          <div className="text-xs uppercase tracking-widest text-muted">{t("joinSession")}</div>
          <div className="flex gap-2">
            <input
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 4))}
              placeholder="CODE"
              className="flex-1 border border-ink px-3 py-3 font-display text-2xl tracking-[0.3em] uppercase"
              inputMode="text"
              autoCapitalize="characters"
            />
            <button type="submit" disabled={code.length !== 4} className="bg-ink text-paper px-4">
              {t("join")}
            </button>
          </div>
          <button type="button" onClick={scan} className="border border-rule py-2 text-sm">
            {t("scanQr")}
          </button>
          {scanHint && <p className="text-xs text-muted">{scanHint}</p>}
        </form>
      </section>

      <section className="grid sm:grid-cols-3 gap-3 text-sm">
        <Link href="/decks/new" className="border border-ink px-4 py-3 hover:bg-ink hover:text-paper">
          {t("newDeck")}
        </Link>
        <Link href="/explore?tab=decks" className="border border-ink px-4 py-3 hover:bg-ink hover:text-paper">
          {t("forkDeck")}
        </Link>
        <Link href="/explore" className="border border-ink px-4 py-3 hover:bg-ink hover:text-paper">
          {t("browseBase")}
        </Link>
      </section>

      {signedIn && (
        <>
          <section>
            <h2 className="font-display text-2xl mb-3">{t("yourDecks")}</h2>
            {decks === null ? (
              <p className="text-sm text-muted">…</p>
            ) : decks.length === 0 ? (
              <p className="text-sm text-muted">{t("noDecks")}</p>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {decks.map((d) => (
                  <DeckTile
                    key={d.id}
                    deck={d}
                    chips={[
                      `${d.stats?.cards ?? 0} ${t("chipCards")}`,
                      ...(d.stats?.positions_total ? [`${Math.max(0, d.stats.positions_total - (d.stats.filled_positions ?? 0))} ${t("chipEmpty")}`] : []),
                      ...(d.stats?.needs_readings ? [`${d.stats.needs_readings} ${t("chipNeedsReadings")}`] : []),
                      ...(d.stats?.open_proposals ? [`${d.stats.open_proposals} ${t("chipProposals")}`] : []),
                    ]}
                  />
                ))}
              </div>
            )}
          </section>
          {inbox && (inbox.to_read.length + inbox.open_for_edit.length + inbox.requests.length > 0) && (
            <section>
              <h2 className="font-display text-2xl mb-3">{t("waiting")}</h2>
              <div className="grid md:grid-cols-3 gap-4 text-sm">
                {(["to_read", "open_for_edit", "requests"] as const).map((k) => (
                  <div key={k} className="border border-rule p-3">
                    <div className="text-xs uppercase tracking-widest text-muted mb-2">{t(`inbox_${k}`)}</div>
                    {inbox[k].length === 0 && <p className="text-muted">—</p>}
                    <ul className="flex flex-col gap-1">
                      {inbox[k].map((c) => (
                        <li key={c.id}>
                          <Link href={`/d/${c.deck_id}/cards/${c.id}`} className="underline underline-offset-2">
                            {c.title ?? c.position_key}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          )}
          <section>
            <h2 className="font-display text-2xl mb-3">{t("activity")}</h2>
            {activity && activity.length > 0 ? (
              <ul className="text-sm flex flex-col gap-1">
                {activity.slice(0, 20).map((a) => (
                  <li key={a.id} className="flex gap-2">
                    <span className="text-muted tabular-nums text-xs w-32 shrink-0">{a.created_at.slice(0, 16).replace("T", " ")}</span>
                    <span>
                      <b>{a.actor_name ?? a.actor_id}</b> · {a.kind}
                      {a.refs?.card_id && (
                        <>
                          {" · "}
                          <Link href={`/d/${a.deck_id}/cards/${a.refs.card_id}`} className="underline">
                            {a.refs.position_key ?? a.refs.card_id}
                          </Link>
                        </>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">{t("noActivity")}</p>
            )}
          </section>
          <p className="text-xs text-muted">
            {t("signedInAs")} {me?.name}
          </p>
        </>
      )}
    </div>
  );
}

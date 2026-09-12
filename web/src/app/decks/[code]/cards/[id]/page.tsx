"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Chain from "@/components/Chain";
import CardFace from "@/components/CardFace";
import VerdictBadge from "@/components/VerdictBadge";
import { api, Chain as ChainT, getGuestId, Verdict } from "@/lib/api";

/** Card page: the full chain plus the Maker's approved-editors control (Makers approve people, never edits). */
export default function CardPage() {
  const params = useParams<{ code: string; id: string }>();
  const code = (params?.code ?? "PLAY").toString().toUpperCase();
  const id = (params?.id ?? "").toString();
  const [chain, setChain] = useState<ChainT | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [guest, setGuest] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    api
      .deckCard(code, id)
      .then(setChain)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [code, id]);
  useEffect(() => {
    setGuest(getGuestId());
    load();
  }, [load]);

  if (err && !chain) return <p className="pt-10 text-sm text-accent">{err}</p>;
  if (!chain) return <p className="pt-10 text-sm text-muted">Loading…</p>;
  const { card } = chain;
  const isMaker = guest !== null && card.maker_id === guest;
  const last = chain.versions[chain.versions.length - 1];
  const verdict = (last as unknown as { verdict?: Verdict })?.verdict;

  async function setApproved(v: "*" | string[]) {
    if (!guest) return;
    setSaving(true);
    try {
      setChain(await api.setApprovedEditors(code, id, guest, v));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="pt-6 flex flex-col gap-6">
      <header>
        <div className="text-xs uppercase tracking-widest text-muted">
          <Link href={`/decks/${code}`} className="underline underline-offset-2">
            deck {code}
          </Link>{" "}
          · card
        </div>
        <h1 className="font-display text-2xl mt-1">{card.title ?? "Untitled card"}</h1>
      </header>
      {last && (
        <div className="flex gap-4 items-start">
          <CardFace elements={last.elements} size="phone" />
          <div className="text-sm flex flex-col gap-2 min-w-0">
            <div className="text-xs text-muted">
              latest v{last.v} · F {last.fidelity === null ? "–" : last.fidelity.toFixed(2)} · n {last.n_readings}
            </div>
            {verdict && <VerdictBadge verdict={verdict} showStats={false} />}
            {isMaker && card.status !== "landed" && card.status !== "closed" && (
              <div className="border border-rule p-2 text-xs flex flex-col gap-1">
                <div className="uppercase tracking-widest text-muted">who may edit your card</div>
                <p className="text-muted">You decide who takes a turn. You never decide which edits land.</p>
                <div className="flex gap-2">
                  <button disabled={saving} onClick={() => setApproved("*")} className={`border px-2 py-1 ${card.approved_editors === "*" ? "bg-ink text-paper border-ink" : "border-rule"}`}>
                    anyone in the deck
                  </button>
                  <button disabled={saving} onClick={() => setApproved([])} className={`border px-2 py-1 ${Array.isArray(card.approved_editors) ? "bg-ink text-paper border-ink" : "border-rule"}`}>
                    a list
                  </button>
                </div>
                {Array.isArray(card.approved_editors) && (
                  <p className="text-muted">
                    approved: {card.approved_editors.length ? card.approved_editors.join(", ") : "nobody yet — edit the list from the deck's member ids"}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
      <Chain chain={chain} />
      {err && <p className="text-xs text-accent">{err}</p>}
    </section>
  );
}

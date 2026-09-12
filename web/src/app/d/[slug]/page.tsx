"use client";
import Link from "next/link";
import { useTranslations } from "next-intl";
import Share from "@/components/Share";
import { useDeckCtx } from "@/components/ws/DeckContext";
import { v5 } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export default function OverviewPage() {
  const t = useTranslations("overview");
  const { deck, atLeast } = useDeckCtx();
  const activity = useLoad(() => v5.decks.activity(deck.id), [deck.id]);
  const s = deck.stats ?? ({} as typeof deck.stats);
  const stat = (label: string, v: string | number | null | undefined) => (
    <div className="border border-rule p-3">
      <div className="text-[10px] uppercase tracking-widest text-muted">{label}</div>
      <div className="font-display text-2xl">{v ?? "—"}</div>
    </div>
  );
  return (
    <div className="flex flex-col gap-8">
      <p className="text-sm max-w-prose">{deck.description || <span className="text-muted">{t("noDescription")}</span>}</p>
      <div className="text-xs flex flex-wrap items-center gap-2">
        <span className="uppercase tracking-widest text-muted">{t("lineage")}</span>
        {deck.lineage?.ancestors?.map((a) => (
          <Link key={a.deck_id} href={`/d/${a.slug ?? a.deck_id}`} className="underline">
            {a.name ?? a.deck_id}
          </Link>
        ))}
        {deck.lineage?.ancestors?.length ? <span>→</span> : null}
        <b>{deck.name}</b>
        {deck.lineage?.children?.length ? <span>→</span> : null}
        {deck.lineage?.children?.map((c) => (
          <Link key={c.deck_id} href={`/d/${c.slug ?? c.deck_id}`} className="underline">
            {c.name ?? c.deck_id}
          </Link>
        ))}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {stat(t("cards"), s.positions_total ? `${s.filled_positions ?? s.cards} / ${s.positions_total}` : s.cards)}
        {stat(t("symbols"), s.symbols)}
        {stat(t("readings"), s.readings)}
        {stat(t("forks"), s.forks)}
        {stat(t("coherence"), s.coherence_index != null ? s.coherence_index.toFixed(2) : null)}
        {stat(t("meanFidelity"), s.mean_fidelity != null ? s.mean_fidelity.toFixed(2) : null)}
        {stat(t("sessions"), s.sessions)}
        {stat(t("needsReadings"), s.needs_readings)}
      </div>
      <div className="flex flex-wrap gap-2 text-sm">
        <Link href={`/d/${deck.slug}/cards`} className="border border-ink px-3 py-1.5">
          {t("openCards")}
        </Link>
        <Link href={`/d/${deck.slug}/read`} className="border border-ink px-3 py-1.5">
          {t("readACard")}
        </Link>
        <Link href={`/d/${deck.slug}/grammar`} className="border border-ink px-3 py-1.5">
          {t("openGrammar")}
        </Link>
        {atLeast("member") && (
          <Link href={`/d/${deck.slug}/play`} className="border border-ink px-3 py-1.5">
            {t("hostSession")}
          </Link>
        )}
        {deck.settings?.allow_forks && (
          <button type="button" className="border border-rule px-3 py-1.5" onClick={() => v5.decks.fork(deck.id).then((d) => (window.location.href = `/d/${d.slug}`))}>
            {t("fork")}
          </button>
        )}
      </div>
      <section>
        <h2 className="font-display text-xl mb-2">{t("share")}</h2>
        <Share path={`/d/${deck.slug}`} token={deck.visibility === "unlisted" ? deck.share_token : null} />
      </section>
      <section>
        <h2 className="font-display text-xl mb-2">{t("activity")}</h2>
        <ul className="text-sm flex flex-col gap-1">
          {activity.data?.slice(0, 30).map((a) => (
            <li key={a.id} className="flex gap-2">
              <span className="text-muted tabular-nums text-xs w-32 shrink-0">{a.created_at?.slice(0, 16).replace("T", " ")}</span>
              <span>
                <b>{a.actor_name ?? a.actor_id}</b> · {a.kind}
                {a.refs?.card_id && (
                  <>
                    {" · "}
                    <Link href={`/d/${deck.slug}/cards/${a.refs.card_id}`} className="underline">
                      {a.refs.position_key ?? a.refs.card_id}
                    </Link>
                  </>
                )}
              </span>
            </li>
          ))}
          {activity.data?.length === 0 && <li className="text-muted">{t("noActivity")}</li>}
        </ul>
      </section>
    </div>
  );
}

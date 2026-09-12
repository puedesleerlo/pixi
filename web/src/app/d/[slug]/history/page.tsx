"use client";
import Link from "next/link";
import { useState } from "react";
import { useTranslations } from "next-intl";
import ErrorState from "@/components/ErrorState";
import { useDeckCtx } from "@/components/ws/DeckContext";
import { v5 } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export default function HistoryPage() {
  const t = useTranslations("history");
  const { deck, atLeast } = useDeckCtx();
  const [tab, setTab] = useState<"versions" | "lineage" | "upstream">("versions");
  const activity = useLoad(() => v5.decks.activity(deck.id), [deck.id]);
  const lineage = useLoad(() => v5.decks.lineage(deck.id), [deck.id]);
  const upstream = useLoad(() => v5.decks.upstreamProposals(deck.id).catch(() => []), [deck.id]);
  const versions = (activity.data ?? []).filter((a) => /version|edit|generate|landed|closed/.test(a.kind));
  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2 text-sm">
        {(["versions", "lineage", "upstream"] as const).map((k) => (
          <button key={k} type="button" onClick={() => setTab(k)} className={`border px-3 py-1 ${tab === k ? "border-ink bg-ink text-paper" : "border-rule"}`}>
            {t(`tab_${k}`)}
          </button>
        ))}
      </div>
      {tab === "versions" && (
        <ul className="text-sm flex flex-col gap-1">
          {activity.error && <ErrorState error={activity.error} status={activity.status} />}
          {versions.map((a) => (
            <li key={a.id} className="flex gap-2">
              <span className="text-muted tabular-nums text-xs w-32 shrink-0">{a.created_at?.slice(0, 16).replace("T", " ")}</span>
              <span>
                <b>{a.actor_name ?? a.actor_id}</b> · {a.kind}
                {a.refs?.op && ` · ${a.refs.op}`}
                {a.refs?.bet_axis && ` · bet ${a.refs.bet_axis}`}
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
          {activity.data && versions.length === 0 && <li className="text-muted">{t("empty")}</li>}
        </ul>
      )}
      {tab === "lineage" && (
        <div className="text-sm flex flex-col gap-2">
          {lineage.error && <ErrorState error={lineage.error} status={lineage.status} />}
          <div>
            {t("ancestors")}:{" "}
            {lineage.data?.ancestors?.length ? (
              lineage.data.ancestors.map((a) => (
                <Link key={a.deck_id} href={`/d/${a.slug ?? a.deck_id}`} className="underline mr-2">
                  {a.name ?? a.deck_id}
                </Link>
              ))
            ) : (
              <span className="text-muted">—</span>
            )}
          </div>
          <div className="font-display">{deck.name}</div>
          <div>
            {t("forks")}:{" "}
            {lineage.data?.children?.length ? (
              lineage.data.children.map((a) => (
                <Link key={a.deck_id} href={`/d/${a.slug ?? a.deck_id}`} className="underline mr-2">
                  {a.name ?? a.deck_id}
                </Link>
              ))
            ) : (
              <span className="text-muted">—</span>
            )}
          </div>
          {deck.origin?.kind === "fork" && atLeast("curator") && (
            <button type="button" className="self-start border border-ink px-3 py-1.5 text-xs" onClick={() => v5.decks.syncFromParent(deck.id).then(() => lineage.refresh())}>
              {t("syncFromParent")}
            </button>
          )}
        </div>
      )}
      {tab === "upstream" && (
        <ul className="text-sm flex flex-col gap-2">
          {upstream.data?.map((p) => (
            <li key={p.id} className="border border-rule p-3 flex flex-col gap-1">
              <div>
                {p.kind} · {p.status} · {t("from")} {p.from_deck_id}
              </div>
              <div className="text-xs text-muted">“{p.note}”</div>
              {p.status === "open" && atLeast("curator") && p.to_deck_id === deck.id && (
                <div className="flex gap-2 text-xs">
                  <button type="button" className="bg-ink text-paper px-2 py-1" onClick={() => v5.upstream.decide(p.id, { status: "accepted" }).then(upstream.refresh)}>
                    {t("accept")}
                  </button>
                  <button type="button" className="border border-rule px-2 py-1" onClick={() => v5.upstream.decide(p.id, { status: "declined", decision_note: window.prompt(t("declineNote")) ?? "" }).then(upstream.refresh)}>
                    {t("decline")}
                  </button>
                </div>
              )}
            </li>
          ))}
          {upstream.data?.length === 0 && <li className="text-muted">{t("noProposals")}</li>}
        </ul>
      )}
    </div>
  );
}

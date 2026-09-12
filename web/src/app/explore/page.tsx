"use client";
import Link from "next/link";
import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import DeckTile from "@/components/DeckTile";
import ErrorState from "@/components/ErrorState";
import StatusChip from "@/components/StatusChip";
import { v5 } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

function ExploreInner() {
  const t = useTranslations("explore");
  const sp = useSearchParams();
  const [tab, setTab] = useState<"base" | "decks">(sp.get("tab") === "decks" ? "decks" : "base");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("coherence");
  const [structure, setStructure] = useState("");
  const base = useLoad(() => v5.baseDecks.list(), []);
  const decks = useLoad(() => v5.decks.list({ visibility: "public", sort }), [sort]);
  const ql = q.trim().toLowerCase();
  const baseList = useMemo(() => (base.data ?? []).filter((b) => !ql || `${b.name} ${b.tradition} ${b.year}`.toLowerCase().includes(ql)), [base.data, ql]);
  const deckList = useMemo(
    () => (decks.data ?? []).filter((d) => (!ql || `${d.name} ${d.description}`.toLowerCase().includes(ql)) && (!structure || d.structure_template_id === structure)),
    [decks.data, ql, structure],
  );
  return (
    <div className="max-w-6xl mx-auto px-4 py-8 flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="font-display text-3xl">{t("title")}</h1>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="border border-rule px-3 py-2 text-sm w-64" />
      </div>
      <div className="flex gap-2 text-sm">
        {(["base", "decks"] as const).map((k) => (
          <button key={k} type="button" onClick={() => setTab(k)} className={`border px-3 py-1 ${tab === k ? "border-ink bg-ink text-paper" : "border-rule"}`}>
            {t(`tab_${k}`)}
          </button>
        ))}
      </div>
      {tab === "base" && (
        <section>
          {base.error && <ErrorState error={base.error} status={base.status} />}
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {baseList.map((b) => (
              <div key={b.slug} className="border border-rule p-3 flex flex-col gap-1 bg-[#faf6ee]">
                <div className="flex items-baseline justify-between gap-2">
                  <Link href={`/base/${b.slug}`} className="font-display text-lg underline-offset-2 hover:underline">
                    {b.name}
                  </Link>
                  <StatusChip value={b.status} />
                </div>
                <div className="text-xs text-muted">
                  {b.tradition} · {b.year} · {b.card_count} {t("cards")}
                </div>
                <div className="text-[11px] text-muted line-clamp-2">{b.rights_note}</div>
                <Link href={`/decks/new?base=${b.slug}`} className="self-start mt-1 text-xs border border-ink px-2 py-1">
                  {t("startFrom")}
                </Link>
              </div>
            ))}
            {base.data && baseList.length === 0 && <p className="text-sm text-muted">{t("none")}</p>}
          </div>
        </section>
      )}
      {tab === "decks" && (
        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-2 text-xs items-center">
            <span className="text-muted">{t("sort")}</span>
            {["coherence", "cards", "forks", "recent"].map((s) => (
              <button key={s} type="button" onClick={() => setSort(s)} className={`border px-2 py-1 ${sort === s ? "border-ink bg-ink text-paper" : "border-rule"}`}>
                {t(`sort_${s}`)}
              </button>
            ))}
            <select value={structure} onChange={(e) => setStructure(e.target.value)} className="border border-rule px-2 py-1 bg-transparent">
              <option value="">{t("anyStructure")}</option>
              {["tarot78", "majors22", "minors56", "lenormand36", "mantegna50", "free"].map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          {decks.error && <ErrorState error={decks.error} status={decks.status} />}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {deckList.map((d) => (
              <DeckTile key={d.id} deck={d} chips={[`${d.stats?.cards ?? 0} ${t("cards")}`, `${d.stats?.forks ?? 0} forks`, ...(d.stats?.coherence_index != null ? [`coh ${d.stats.coherence_index.toFixed(2)}`] : [])]} />
            ))}
          </div>
          {decks.data && deckList.length === 0 && <p className="text-sm text-muted">{t("none")}</p>}
        </section>
      )}
    </div>
  );
}

export default function ExplorePage() {
  return (
    <Suspense fallback={null}>
      <ExploreInner />
    </Suspense>
  );
}

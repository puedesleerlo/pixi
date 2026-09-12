"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import CardTile from "@/components/CardTile";
import ErrorState from "@/components/ErrorState";
import { useDeckCtx } from "@/components/ws/DeckContext";
import { v5 } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { Card, StructurePosition, StructureTemplate } from "@/lib/types";

const FILTERS = ["all", "needs_readings", "open", "landed", "closed", "contested", "off_style", "mine"] as const;
type Filter = (typeof FILTERS)[number];

export default function CardsPage() {
  const t = useTranslations("cards");
  const { deck, me, atLeast } = useDeckCtx();
  const cards = useLoad(() => v5.cards.list(deck.id), [deck.id]);
  const structure = useLoad<StructureTemplate>(async () => deck.structure ?? (await v5.structures.get(deck.structure_template_id)), [deck.id, deck.structure_template_id]);
  const [filter, setFilter] = useState<Filter>("all");
  const canCreate = atLeast("curator") || (atLeast("member") && deck.settings?.who_can_create_cards !== "curators");
  const byPos = useMemo(() => {
    const m = new Map<string, Card>();
    for (const c of cards.data ?? []) if (c.status !== "archived") m.set(c.position_key, c);
    return m;
  }, [cards.data]);
  const keep = (c: Card) => {
    switch (filter) {
      case "needs_readings":
        return c.status === "reading";
      case "open":
        return c.status === "open";
      case "landed":
        return c.status === "landed";
      case "closed":
        return c.status === "closed";
      case "contested":
        return !!c.contested;
      case "off_style":
        return !!c.off_style;
      case "mine":
        return !!me && c.maker_id === me.id;
      default:
        return true;
    }
  };
  const groups = useMemo(() => {
    const st = structure.data;
    if (!st || st.key === "free") return null;
    const g = new Map<string, StructurePosition[]>();
    for (const p of st.positions) g.set(p.group, [...(g.get(p.group) ?? []), p]);
    return g;
  }, [structure.data]);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1 text-xs">
          {FILTERS.map((f) => (
            <button key={f} type="button" onClick={() => setFilter(f)} className={`border px-2 py-1 ${filter === f ? "border-ink bg-ink text-paper" : "border-rule"}`}>
              {t(`filter_${f}`)}
            </button>
          ))}
        </div>
        <div className="flex gap-2 text-xs">
          {canCreate && (!groups || filter === "all") && (
            <Link href={`/d/${deck.slug}/cards/new`} className="border border-ink px-2 py-1">
              {t("newCard")}
            </Link>
          )}
          {atLeast("curator") && deck.origin?.kind === "base" && (
            <Link href={`/d/${deck.slug}/cards/reinterpret`} className="border border-ink px-2 py-1">
              {t("reinterpret")}
            </Link>
          )}
        </div>
      </div>
      {cards.error && <ErrorState error={cards.error} status={cards.status} />}
      {groups ? (
        [...groups.entries()].map(([group, positions]) => (
          <section key={group}>
            <h2 className="font-display text-lg mb-2">{group}</h2>
            <div className="grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-7 gap-2">
              {positions
                .sort((a, b) => a.order - b.order)
                .map((p) => {
                  const c = byPos.get(p.key);
                  if (c) return keep(c) ? <CardTile key={p.key} deckSlug={deck.slug} card={c} position={p} /> : null;
                  if (filter !== "all") return null;
                  return canCreate ? (
                    <Link key={p.key} href={`/d/${deck.slug}/cards/new?position=${p.key}`} className="aspect-[11/19] border border-dashed border-rule flex flex-col items-center justify-center text-xs text-muted hover:border-ink hover:text-ink">
                      <span className="text-2xl">+</span>
                      <span className="px-1 text-center">{p.title}</span>
                    </Link>
                  ) : (
                    <div key={p.key} className="aspect-[11/19] border border-dashed border-rule flex items-center justify-center text-[10px] text-muted px-1 text-center">
                      {p.title}
                    </div>
                  );
                })}
            </div>
          </section>
        ))
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-7 gap-2">
          {(cards.data ?? []).filter((c) => c.status !== "archived" && keep(c)).map((c) => (
            <CardTile key={c.id} deckSlug={deck.slug} card={c} />
          ))}
        </div>
      )}
      {cards.data && cards.data.length === 0 && !groups && <p className="text-sm text-muted">{t("empty")}</p>}
    </div>
  );
}

"use client";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useTranslations } from "next-intl";
import ErrorState from "@/components/ErrorState";
import { DeckContext } from "@/components/ws/DeckContext";
import WorkspaceNav from "@/components/ws/WorkspaceNav";
import { useDeck, useMe, useRole } from "@/lib/hooks";

function Workspace({ children }: { children: React.ReactNode }) {
  const t = useTranslations("ws");
  const { slug } = useParams<{ slug: string }>();
  const sp = useSearchParams();
  const me = useMe();
  const deck = useDeck(slug, sp.get("share_token"));
  const { role, atLeast, members } = useRole(deck.data, me.data);
  if (deck.error) return <div className="max-w-6xl mx-auto px-4"><ErrorState error={deck.error} status={deck.status} /></div>;
  if (!deck.data) return <div className="max-w-6xl mx-auto px-4 py-10 text-sm text-muted">{t("loading")}</div>;
  const d = deck.data;
  return (
    <DeckContext.Provider value={{ deck: d, me: me.data, role, atLeast, members, refresh: deck.refresh }}>
      <div className="max-w-6xl mx-auto px-4 py-6">
        <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-5">
          <Link href={`/d/${d.slug}`} className="font-display text-2xl">
            {d.name}
          </Link>
          <span className="text-xs uppercase tracking-wider text-muted">{d.visibility}</span>
          <span className="text-xs text-muted">{d.structure_template_id}</span>
          {d.origin?.kind === "fork" && (
            <span className="text-xs text-muted">
              {t("forkOf")} {d.lineage?.ancestors?.[0]?.name ?? d.origin.forked_from_deck_id}
            </span>
          )}
          {d.origin?.kind === "base" && <span className="text-xs text-muted">{t("fromBase", { base: d.origin.base_deck_id ?? "" })}</span>}
        </header>
        <div className="flex gap-6 pb-14 md:pb-0">
          <WorkspaceNav />
          <section className="flex-1 min-w-0">{children}</section>
        </div>
      </div>
    </DeckContext.Provider>
  );
}

export default function DeckLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={null}>
      <Workspace>{children}</Workspace>
    </Suspense>
  );
}

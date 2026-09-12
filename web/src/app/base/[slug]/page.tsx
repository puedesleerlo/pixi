"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import ErrorState from "@/components/ErrorState";
import MiniBars from "@/components/MiniBars";
import StatusChip from "@/components/StatusChip";
import { imageSrc, v5 } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export default function BaseDeckPage() {
  const t = useTranslations("explore");
  const { slug } = useParams<{ slug: string }>();
  const deck = useLoad(() => v5.baseDecks.get(slug), [slug]);
  const cards = useLoad(() => v5.baseDecks.cards(slug), [slug]);
  const symbols = useLoad(() => v5.baseDecks.symbols(slug), [slug]);
  if (deck.error) return <ErrorState error={deck.error} status={deck.status} />;
  const b = deck.data;
  return (
    <div className="max-w-6xl mx-auto px-4 py-8 flex flex-col gap-6">
      {b && (
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-widest text-muted">{t("baseDeck")}</div>
            <h1 className="font-display text-3xl">{b.name}</h1>
            <div className="text-sm text-muted mt-1">
              {b.tradition} · {b.year} · {b.origin} · <StatusChip value={b.status} />
            </div>
            <p className="text-xs text-muted mt-2 max-w-prose">{b.rights_note}</p>
            <div className="text-[11px] text-muted mt-1 flex flex-wrap gap-2">
              {b.source_urls?.map((u) => (
                <a key={u} href={u} className="underline" target="_blank" rel="noreferrer">
                  {u.replace(/^https?:\/\//, "").slice(0, 40)}
                </a>
              ))}
            </div>
          </div>
          <Link href={`/decks/new?base=${b.slug}`} className="bg-ink text-paper px-4 py-2 text-sm">
            {t("startFrom")}
          </Link>
        </header>
      )}
      <section>
        <h2 className="font-display text-xl mb-2">
          {t("cards")} {cards.data ? `· ${cards.data.length}` : ""}
        </h2>
        {cards.error && <ErrorState error={cards.error} status={cards.status} />}
        <div className="grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-8 gap-2">
          {cards.data?.map((c) => (
            <figure key={c.id} className="text-[10px]">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imageSrc(c.thumb_url ?? c.image_url) ?? ""} alt={c.title} className="w-full border border-rule" loading="lazy" />
              <figcaption className="mt-0.5 leading-tight">
                <b>{c.title}</b>
                <div className="text-muted">{c.caption}</div>
              </figcaption>
            </figure>
          ))}
        </div>
      </section>
      <section>
        <h2 className="font-display text-xl mb-2">
          {t("registry")} {symbols.data ? `· ${symbols.data.length}` : ""}
        </h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2 text-xs">
          {symbols.data?.map((s) => (
            <div key={s.key ?? s.id} className="border border-rule p-2 flex gap-2">
              {s.exemplar?.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={imageSrc(s.exemplar.image_url) ?? ""} alt="" className="w-12 h-12 object-contain border border-rule bg-white" />
              ) : (
                <div className="w-12 h-12 border border-rule bg-[#faf6ee]" />
              )}
              <div className="min-w-0 flex-1">
                <div className="font-medium">{s.name}</div>
                <div className="text-muted line-clamp-2">{s.gloss}</div>
                {s.prior_axes && <MiniBars axes={s.prior_axes} width={80} />}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

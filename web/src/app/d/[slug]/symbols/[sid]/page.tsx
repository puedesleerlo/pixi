"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import ErrorState from "@/components/ErrorState";
import MiniBars from "@/components/MiniBars";
import StatusChip from "@/components/StatusChip";
import { useDeckCtx } from "@/components/ws/DeckContext";
import { imageSrc, v5 } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export default function SymbolDetailPage() {
  const t = useTranslations("symbols");
  const { deck } = useDeckCtx();
  const { sid } = useParams<{ sid: string }>();
  const s = useLoad(() => v5.symbols.get(sid), [sid]);
  if (s.error) return <ErrorState error={s.error} status={s.status} />;
  if (!s.data) return null;
  const sym = s.data;
  return (
    <div className="flex flex-col gap-6 max-w-2xl">
      <header className="flex gap-4 items-start">
        {sym.exemplar?.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imageSrc(sym.exemplar.image_url) ?? ""} alt="" className="w-24 h-24 object-contain border border-rule bg-white" />
        ) : (
          <div className="w-24 h-24 border border-rule bg-[#faf6ee]" />
        )}
        <div>
          <div className="text-xs uppercase tracking-widest text-muted">{t("symbol")}</div>
          <h1 className="font-display text-2xl">{sym.name}</h1>
          <p className="text-sm text-muted">{sym.gloss}</p>
          <div className="flex gap-1 mt-1">
            <StatusChip value={sym.status} />
            <StatusChip value={sym.measured?.coherence ?? "untested"} />
            <span className="text-[10px] text-muted self-center">{sym.origin} · {sym.placement}</span>
          </div>
        </div>
      </header>
      <section className="grid sm:grid-cols-2 gap-4 text-xs">
        <div>
          <div className="uppercase tracking-widest text-muted mb-1">{t("declared")}</div>
          <MiniBars axes={sym.declared_axes} width={220} labels />
          <p className="mt-1">{sym.declared_text}</p>
        </div>
        <div>
          <div className="uppercase tracking-widest text-muted mb-1">
            {t("measured")} · n {sym.measured?.n_readings ?? 0} · {t("edits")} {sym.measured?.n_edits ?? 0}
          </div>
          {sym.measured?.n_readings > 0 ? <MiniBars axes={sym.measured.coef} lo={sym.measured.ci_low} hi={sym.measured.ci_high} prior={sym.prior_axes} color="#c8361e" width={220} labels /> : <p className="text-muted">{t("untested")}</p>}
          {sym.measured?.declared_vs_measured != null && (
            <p className="mt-1">
              {t("declaredVsMeasured")}: {sym.measured.declared_vs_measured.toFixed(2)}
            </p>
          )}
          {sym.prior_axes && (
            <p className="text-muted">
              {t("prior")}: {sym.prior_source} ▾
            </p>
          )}
        </div>
      </section>
      <section className="text-sm">
        <h2 className="font-display text-lg mb-1">{t("cardsUsing")}</h2>
        <ul className="flex flex-col gap-1 text-xs">
          {(sym.cards ?? []).map((c) => (
            <li key={c.card_id} className="flex items-center gap-2">
              <Link href={`/d/${deck.slug}/cards/${c.card_id}`} className="underline">
                {c.position_key ?? c.card_id}
              </Link>
              {c.effect && <MiniBars axes={c.effect} width={90} color="#c8361e" />}
              {typeof c.angle === "number" && <span className={c.angle > 45 ? "text-accent" : "text-muted"}>{c.angle.toFixed(0)}°</span>}
            </li>
          ))}
          {(sym.cards ?? []).length === 0 && <li className="text-muted">—</li>}
        </ul>
      </section>
      {sym.attestations?.length > 0 && (
        <section className="text-xs">
          <h2 className="font-display text-lg mb-1">{t("attestations")}</h2>
          <ul className="flex flex-col gap-1">
            {sym.attestations.map((a, i) => (
              <li key={i}>
                <b>{a.source}</b> — {a.note}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

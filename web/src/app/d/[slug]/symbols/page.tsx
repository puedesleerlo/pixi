"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import ErrorState from "@/components/ErrorState";
import MiniBars from "@/components/MiniBars";
import StatusChip from "@/components/StatusChip";
import SymbolForm, { type SymbolDraft } from "@/components/SymbolForm";
import { useDeckCtx } from "@/components/ws/DeckContext";
import { imageSrc, v5 } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { Symbol } from "@/lib/types";

type Panel = "none" | "add" | "propose" | "inbox" | "import";

export default function SymbolsPage() {
  const t = useTranslations("symbols");
  const { deck, atLeast } = useDeckCtx();
  const symbols = useLoad(() => v5.symbols.list(deck.id), [deck.id]);
  const proposals = useLoad(async () => (atLeast("curator") ? v5.symbols.proposals(deck.id, "open") : []), [deck.id, atLeast]);
  const [panel, setPanel] = useState<Panel>("none");
  const [q, setQ] = useState("");
  const [mergeFrom, setMergeFrom] = useState<Symbol | null>(null);
  const [mergeInto, setMergeInto] = useState("");
  const [baseSymbols, setBaseSymbols] = useState<Symbol[]>([]);
  const [importSel, setImportSel] = useState<Set<string>>(new Set());
  const baseSlug = deck.origin?.base_deck_id ?? null;
  useEffect(() => {
    if (panel === "import" && baseSlug) v5.baseDecks.symbols(baseSlug).then(setBaseSymbols).catch(() => setBaseSymbols([]));
  }, [panel, baseSlug]);
  const rows = useMemo(() => (symbols.data ?? []).filter((s) => s.status !== "merged" && (!q || `${s.name} ${s.gloss} ${s.tags.join(" ")}`.toLowerCase().includes(q.toLowerCase()))), [symbols.data, q]);
  const haveKeys = new Set((symbols.data ?? []).map((s) => s.key));

  const draftToBody = (d: SymbolDraft) => ({
    name: d.name,
    gloss: d.gloss,
    tags: d.tags,
    declared_axes: d.declared_axes,
    declared_text: d.declared_text,
    placement: d.placement,
    attestations: d.attestations,
    exemplar_upload: d.exemplar_upload ?? undefined,
    exemplar_from_base_card: d.exemplar_from_base_card ?? undefined,
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="border border-rule px-2 py-1 text-sm" />
        <div className="flex flex-wrap gap-1 text-xs">
          {atLeast("member") && !atLeast("curator") && (
            <button type="button" onClick={() => setPanel(panel === "propose" ? "none" : "propose")} className="border border-ink px-2 py-1">
              {t("propose")}
            </button>
          )}
          {atLeast("curator") && (
            <>
              <button type="button" onClick={() => setPanel(panel === "add" ? "none" : "add")} className="border border-ink px-2 py-1">
                {t("add")}
              </button>
              <button type="button" onClick={() => setPanel(panel === "inbox" ? "none" : "inbox")} className="border border-ink px-2 py-1">
                {t("inbox")} {proposals.data?.length ? `(${proposals.data.length})` : ""}
              </button>
              {baseSlug && (
                <button type="button" onClick={() => setPanel(panel === "import" ? "none" : "import")} className="border border-ink px-2 py-1">
                  {t("importFromBase")}
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {(panel === "add" || panel === "propose") && (
        <div className="border border-rule p-4">
          <div className="font-display text-lg mb-3">{panel === "add" ? t("addTitle") : t("proposeTitle")}</div>
          <SymbolForm
            baseDeckSlug={baseSlug}
            withNote={panel === "propose"}
            submitLabel={panel === "add" ? t("add") : t("propose")}
            onSubmit={async (d, note) => {
              if (panel === "add") await v5.symbols.add(deck.id, draftToBody(d));
              else await v5.symbols.propose(deck.id, { symbol_draft: draftToBody(d), note });
              setPanel("none");
              symbols.refresh();
            }}
          />
        </div>
      )}

      {panel === "inbox" && (
        <div className="border border-rule p-4 flex flex-col gap-3">
          <div className="font-display text-lg">{t("inboxTitle")}</div>
          {proposals.data?.length === 0 && <p className="text-sm text-muted">{t("noProposals")}</p>}
          {proposals.data?.map((p) => (
            <div key={p.id} className="border border-rule p-3 text-sm flex flex-col sm:flex-row gap-3">
              <div className="flex-1">
                <div className="font-medium">{p.symbol_draft.name}</div>
                <div className="text-muted">{p.symbol_draft.gloss}</div>
                {p.note && <div className="text-xs mt-1">“{p.note}”</div>}
                <div className="text-[10px] text-muted mt-1">{p.proposed_by}</div>
              </div>
              <MiniBars axes={p.symbol_draft.declared_axes} />
              <div className="flex gap-2 text-xs">
                <button type="button" className="bg-ink text-paper px-2 py-1" onClick={() => v5.symbols.decide(p.id, { status: "approved" }).then(() => (proposals.refresh(), symbols.refresh()))}>
                  {t("approve")}
                </button>
                <button
                  type="button"
                  className="border border-rule px-2 py-1"
                  onClick={() => {
                    const note = window.prompt(t("declineNote")) ?? "";
                    v5.symbols.decide(p.id, { status: "declined", decision_note: note }).then(proposals.refresh);
                  }}
                >
                  {t("decline")}
                </button>
              </div>
            </div>
          ))}
          <p className="text-[11px] text-muted">{t("notAVote")}</p>
        </div>
      )}

      {panel === "import" && (
        <div className="border border-rule p-4 flex flex-col gap-3">
          <div className="font-display text-lg">{t("importFromBase")}</div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-1 max-h-64 overflow-auto text-xs">
            {baseSymbols.map((s) => (
              <label key={s.key} className={`flex items-center gap-2 ${haveKeys.has(s.key) ? "text-muted" : ""}`}>
                <input
                  type="checkbox"
                  disabled={haveKeys.has(s.key)}
                  checked={importSel.has(s.key)}
                  onChange={(e) => {
                    const n = new Set(importSel);
                    if (e.target.checked) n.add(s.key);
                    else n.delete(s.key);
                    setImportSel(n);
                  }}
                />
                {s.name} {haveKeys.has(s.key) && `· ${t("already")}`}
              </label>
            ))}
          </div>
          <button
            type="button"
            disabled={importSel.size === 0}
            className="self-start bg-ink text-paper px-3 py-1.5 text-sm"
            onClick={() => v5.symbols.importFromBase(deck.id, { base_deck_slug: baseSlug!, symbol_keys: [...importSel] }).then(() => (setPanel("none"), symbols.refresh()))}
          >
            {t("importN", { n: importSel.size })}
          </button>
        </div>
      )}

      {mergeFrom && (
        <div className="border border-accent p-3 text-sm flex flex-wrap items-center gap-2">
          {t("mergeInto", { name: mergeFrom.name })}
          <select value={mergeInto} onChange={(e) => setMergeInto(e.target.value)} className="border border-rule px-2 py-1 bg-transparent">
            <option value="">—</option>
            {rows.filter((s) => s.id !== mergeFrom.id && s.status === "active").map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <button type="button" disabled={!mergeInto} className="bg-ink text-paper px-2 py-1 text-xs" onClick={() => v5.symbols.merge(mergeFrom.id, mergeInto).then(() => (setMergeFrom(null), symbols.refresh()))}>
            {t("merge")}
          </button>
          <button type="button" className="underline text-xs" onClick={() => setMergeFrom(null)}>
            {t("cancel")}
          </button>
        </div>
      )}

      {symbols.error && <ErrorState error={symbols.error} status={symbols.status} />}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-[10px] uppercase tracking-wider text-muted text-left">
            <tr>
              <th className="py-1 pr-2"></th>
              <th className="py-1 pr-2">{t("name")}</th>
              <th className="py-1 pr-2">{t("declared")}</th>
              <th className="py-1 pr-2">{t("measured")}</th>
              <th className="py-1 pr-2">{t("cards")}</th>
              <th className="py-1 pr-2">{t("coherence")}</th>
              <th className="py-1 pr-2">{t("origin")}</th>
              <th className="py-1 pr-2">{t("prior")}</th>
              {atLeast("curator") && <th className="py-1"></th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id} className={`border-t border-rule align-top ${s.status === "retired" ? "opacity-50" : ""}`}>
                <td className="py-2 pr-2">
                  {s.exemplar?.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={imageSrc(s.exemplar.image_url) ?? ""} alt="" className="w-10 h-10 object-contain border border-rule bg-white" />
                  ) : (
                    <div className="w-10 h-10 border border-rule bg-[#faf6ee]" />
                  )}
                </td>
                <td className="py-2 pr-2 min-w-[140px]">
                  <Link href={`/d/${deck.slug}/symbols/${s.id}`} className="font-medium underline-offset-2 hover:underline">
                    {s.name}
                  </Link>
                  <div className="text-muted line-clamp-2">{s.gloss}</div>
                  {s.status !== "active" && <StatusChip value={s.status} />}
                </td>
                <td className="py-2 pr-2">
                  <MiniBars axes={s.declared_axes} width={90} />
                </td>
                <td className="py-2 pr-2">
                  {s.measured?.n_readings > 0 ? <MiniBars axes={s.measured.coef} lo={s.measured.ci_low} hi={s.measured.ci_high} prior={s.prior_axes} color="#c8361e" width={90} /> : <span className="text-muted">{t("untested")}</span>}
                </td>
                <td className="py-2 pr-2 tabular-nums">{s.cards_using ?? s.measured?.n_cards ?? 0}</td>
                <td className="py-2 pr-2">
                  <StatusChip value={s.measured?.coherence ?? "untested"} />
                </td>
                <td className="py-2 pr-2 text-muted">{s.origin}</td>
                <td className="py-2 pr-2 text-muted">{s.prior_source ?? "—"}</td>
                {atLeast("curator") && (
                  <td className="py-2 text-right whitespace-nowrap">
                    {s.status === "active" && (
                      <>
                        <button type="button" className="underline mr-2" onClick={() => setMergeFrom(s)}>
                          {t("merge")}
                        </button>
                        <button type="button" className="underline" onClick={() => v5.symbols.retire(s.id).then(symbols.refresh)}>
                          {t("retire")}
                        </button>
                      </>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {symbols.data && rows.length === 0 && <p className="text-sm text-muted py-4">{t("empty")}</p>}
      </div>
    </div>
  );
}

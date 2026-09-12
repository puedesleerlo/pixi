"use client";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import CropPicker from "@/components/CropPicker";
import Sliders8 from "@/components/Sliders8";
import { v5 } from "@/lib/api";
import type { Axes8, BaseCard, Region, SymbolPlacement } from "@/lib/types";

export interface SymbolDraft {
  name: string;
  gloss: string;
  tags: string[];
  declared_axes: Axes8;
  declared_text: string;
  placement: SymbolPlacement;
  attestations: { source: string; note: string }[];
  exemplar_upload?: string | null; // data URL
  exemplar_from_base_card?: { base_card_id: string; bbox: Region } | null;
}

const PLACEMENTS: SymbolPlacement[] = ["any", "center", "top", "bottom", "left", "right"];

/** One form for Add (curator) and Propose (member): name, gloss, tags, 8 sliders, placement, exemplar. */
export default function SymbolForm({
  baseDeckSlug,
  onSubmit,
  submitLabel,
  withNote = false,
}: {
  baseDeckSlug?: string | null;
  onSubmit: (draft: SymbolDraft, note: string) => Promise<void>;
  submitLabel: string;
  withNote?: boolean;
}) {
  const t = useTranslations("symbols");
  const [d, setD] = useState<SymbolDraft>({ name: "", gloss: "", tags: [], declared_axes: Array(8).fill(0), declared_text: "", placement: "any", attestations: [] });
  const [note, setNote] = useState("");
  const [exemplarMode, setExemplarMode] = useState<"none" | "upload" | "crop">("none");
  const [baseCards, setBaseCards] = useState<BaseCard[]>([]);
  const [cropCard, setCropCard] = useState<BaseCard | null>(null);
  const [bbox, setBbox] = useState<Region | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (exemplarMode === "crop" && baseDeckSlug && baseCards.length === 0) v5.baseDecks.cards(baseDeckSlug).then(setBaseCards).catch(() => {});
  }, [exemplarMode, baseDeckSlug, baseCards.length]);
  const complete = d.name.trim() && d.gloss.trim();
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!complete) return;
        setBusy(true);
        setErr(null);
        try {
          await onSubmit({ ...d, exemplar_from_base_card: exemplarMode === "crop" && cropCard && bbox ? { base_card_id: cropCard.id, bbox } : null, exemplar_upload: exemplarMode === "upload" ? d.exemplar_upload : null }, note);
        } catch (er) {
          setErr(er instanceof Error ? er.message : String(er));
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="grid sm:grid-cols-2 gap-3">
        <label className="text-xs flex flex-col gap-1">
          {t("name")}
          <input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value.slice(0, 60) })} className="border border-ink px-2 py-1.5 text-sm" required />
        </label>
        <label className="text-xs flex flex-col gap-1">
          {t("placement")}
          <select value={d.placement} onChange={(e) => setD({ ...d, placement: e.target.value as SymbolPlacement })} className="border border-ink px-2 py-1.5 text-sm bg-transparent">
            {PLACEMENTS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="text-xs flex flex-col gap-1">
        {t("gloss")}
        <input value={d.gloss} onChange={(e) => setD({ ...d, gloss: e.target.value.slice(0, 140) })} className="border border-ink px-2 py-1.5 text-sm" required />
      </label>
      <label className="text-xs flex flex-col gap-1">
        {t("tags")}
        <input value={d.tags.join(", ")} onChange={(e) => setD({ ...d, tags: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} className="border border-rule px-2 py-1.5 text-sm" placeholder="celestial, water" />
      </label>
      <div className="flex flex-col gap-1">
        <div className="text-xs">{t("declaredMeaning")}</div>
        <Sliders8 value={d.declared_axes} onChange={(v) => setD({ ...d, declared_axes: v })} />
        <input value={d.declared_text} onChange={(e) => setD({ ...d, declared_text: e.target.value.slice(0, 140) })} className="border border-rule px-2 py-1.5 text-sm mt-1" placeholder={t("declaredTextPlaceholder")} />
      </div>
      <div className="flex flex-col gap-2">
        <div className="text-xs">{t("exemplar")}</div>
        <div className="flex gap-2 text-xs">
          {(["none", "upload", "crop"] as const).map((m) => (
            <button key={m} type="button" onClick={() => setExemplarMode(m)} className={`border px-2 py-1 ${exemplarMode === m ? "border-ink bg-ink text-paper" : "border-rule"}`} disabled={m === "crop" && !baseDeckSlug}>
              {t(`exemplar_${m}`)}
            </button>
          ))}
        </div>
        {exemplarMode === "upload" && (
          <input
            type="file"
            accept="image/*"
            className="text-xs"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const r = new FileReader();
              r.onload = () => setD({ ...d, exemplar_upload: String(r.result) });
              r.readAsDataURL(f);
            }}
          />
        )}
        {exemplarMode === "crop" && (
          <div className="flex flex-col gap-2">
            <select className="border border-rule px-2 py-1 text-xs bg-transparent max-w-xs" value={cropCard?.id ?? ""} onChange={(e) => setCropCard(baseCards.find((c) => c.id === e.target.value) ?? null)}>
              <option value="">{t("pickBaseCard")}</option>
              {baseCards.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.position_key} · {c.title}
                </option>
              ))}
            </select>
            {cropCard && <CropPicker imageUrl={cropCard.image_url} value={bbox} onChange={setBbox} />}
          </div>
        )}
      </div>
      <label className="text-xs flex flex-col gap-1">
        {t("attestation")}
        <input
          value={d.attestations[0]?.note ?? ""}
          onChange={(e) => setD({ ...d, attestations: e.target.value ? [{ source: "curator", note: e.target.value.slice(0, 200) }] : [] })}
          className="border border-rule px-2 py-1.5 text-sm"
          placeholder={t("attestationPlaceholder")}
        />
      </label>
      {withNote && (
        <label className="text-xs flex flex-col gap-1">
          {t("proposalNote")}
          <textarea value={note} onChange={(e) => setNote(e.target.value.slice(0, 280))} rows={2} className="border border-rule px-2 py-1.5 text-sm" />
        </label>
      )}
      {err && <p className="text-xs text-accent">{err}</p>}
      <button type="submit" disabled={!complete || busy} className="self-start bg-ink text-paper px-4 py-2 text-sm">
        {submitLabel}
      </button>
    </form>
  );
}

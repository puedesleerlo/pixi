"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";
import ErrorState from "@/components/ErrorState";
import { useDeckCtx } from "@/components/ws/DeckContext";
import { v5 } from "@/lib/api";
import type { DeckSettings, StyleGuide, Visibility } from "@/lib/types";

const SECTIONS = ["general", "structure", "style", "permissions", "measurement", "generation", "export", "danger"] as const;

export default function SettingsPage() {
  const t = useTranslations("settings");
  const router = useRouter();
  const { deck, role, atLeast, refresh } = useDeckCtx();
  const [section, setSection] = useState<(typeof SECTIONS)[number]>("general");
  const [general, setGeneral] = useState({ name: deck.name, description: deck.description ?? "", visibility: deck.visibility as Visibility });
  const [structure, setStructure] = useState(deck.structure_template_id);
  const [style, setStyle] = useState<StyleGuide>(deck.style_guide);
  const [settings, setSettings] = useState<DeckSettings>(deck.settings);
  const [msg, setMsg] = useState<string | null>(null);
  const [exportJob, setExportJob] = useState<string | null>(null);
  if (!atLeast("curator")) return <ErrorState error={null} status={403} />;
  const save = (body: Parameters<typeof v5.decks.update>[1]) =>
    v5.decks
      .update(deck.id, body)
      .then(() => {
        setMsg(t("saved"));
        refresh();
      })
      .catch((e) => setMsg(e instanceof Error ? e.message : String(e)));
  const num = (k: keyof DeckSettings, step = 1, min = 0, max = 10000) => (
    <label key={k} className="flex items-center justify-between gap-3 text-sm">
      {t(`k_${k}`)}
      <input type="number" step={step} min={min} max={max} value={Number(settings[k])} onChange={(e) => setSettings({ ...settings, [k]: Number(e.target.value) })} className="border border-rule px-2 py-1 w-28 text-right" />
    </label>
  );
  const bool = (k: keyof DeckSettings) => (
    <label key={k} className="flex items-center justify-between gap-3 text-sm">
      {t(`k_${k}`)}
      <input type="checkbox" checked={!!settings[k]} onChange={(e) => setSettings({ ...settings, [k]: e.target.checked })} />
    </label>
  );
  const visibleSections = SECTIONS.filter((s) => role === "owner" || s === "structure" || s === "style");
  return (
    <div className="flex flex-col md:flex-row gap-6">
      <ul className="flex md:flex-col gap-1 text-sm flex-wrap md:w-40 shrink-0">
        {visibleSections.map((s) => (
          <li key={s}>
            <button type="button" onClick={() => setSection(s)} className={`px-2 py-1 ${section === s ? "bg-ink text-paper" : "hover:bg-[#ece6d8]"}`}>
              {t(`sec_${s}`)}
            </button>
          </li>
        ))}
      </ul>
      <div className="flex-1 max-w-lg flex flex-col gap-3">
        {section === "general" && (
          <>
            <label className="text-xs flex flex-col gap-1">
              {t("name")}
              <input value={general.name} onChange={(e) => setGeneral({ ...general, name: e.target.value })} className="border border-ink px-2 py-1.5" />
            </label>
            <label className="text-xs flex flex-col gap-1">
              {t("description")}
              <textarea value={general.description} onChange={(e) => setGeneral({ ...general, description: e.target.value })} rows={3} className="border border-rule px-2 py-1.5" />
            </label>
            <div className="flex gap-2 text-sm">
              {(["private", "unlisted", "public"] as Visibility[]).map((v) => (
                <button key={v} type="button" onClick={() => setGeneral({ ...general, visibility: v })} className={`border px-3 py-1 ${general.visibility === v ? "border-ink bg-ink text-paper" : "border-rule"}`}>
                  {v}
                </button>
              ))}
            </div>
            <button type="button" className="self-start bg-ink text-paper px-4 py-2 text-sm" onClick={() => save(general)}>
              {t("save")}
            </button>
          </>
        )}
        {section === "structure" && (
          <>
            <select value={structure} onChange={(e) => setStructure(e.target.value)} className="border border-rule px-2 py-1.5 bg-transparent text-sm">
              {["tarot78", "majors22", "minors56", "lenormand36", "mantegna50", "free"].map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <p className="text-xs text-muted">{t("structureWarning")}</p>
            <button type="button" className="self-start bg-ink text-paper px-4 py-2 text-sm" onClick={() => save({ structure_template_id: structure })}>
              {t("save")}
            </button>
          </>
        )}
        {section === "style" && (
          <>
            <label className="text-xs flex flex-col gap-1">
              {t("promptPrefix")}
              <textarea value={style.prompt_prefix} onChange={(e) => setStyle({ ...style, prompt_prefix: e.target.value })} rows={3} className="border border-ink px-2 py-1.5" />
            </label>
            <label className="text-xs flex flex-col gap-1">
              {t("negativePrompt")}
              <input value={style.negative_prompt ?? ""} onChange={(e) => setStyle({ ...style, negative_prompt: e.target.value })} className="border border-rule px-2 py-1.5" />
            </label>
            <div className="flex flex-wrap gap-2 text-xs items-center">
              {t("line")}
              {(["ink", "woodcut", "painted", "flat", "photo", "custom"] as StyleGuide["line"][]).map((l) => (
                <button key={l} type="button" onClick={() => setStyle({ ...style, line: l })} className={`border px-2 py-1 ${style.line === l ? "border-ink bg-ink text-paper" : "border-rule"}`}>
                  {l}
                </button>
              ))}
            </div>
            <div className="flex gap-2 items-center text-xs">
              {t("palette")}
              {(style.palette ?? []).map((c, i) => (
                <input key={i} type="color" value={c} onChange={(e) => setStyle({ ...style, palette: style.palette.map((x, j) => (j === i ? e.target.value : x)) })} />
              ))}
            </div>
            <div className="text-xs text-muted">
              {t("references")}: {style.reference_images?.length ?? 0}
            </div>
            <button type="button" className="self-start bg-ink text-paper px-4 py-2 text-sm" onClick={() => save({ style_guide: style })}>
              {t("save")}
            </button>
          </>
        )}
        {section === "permissions" && (
          <>
            <label className="flex items-center justify-between gap-3 text-sm">
              {t("k_who_can_create_cards")}
              <select value={settings.who_can_create_cards} onChange={(e) => setSettings({ ...settings, who_can_create_cards: e.target.value as DeckSettings["who_can_create_cards"] })} className="border border-rule bg-transparent px-1">
                <option value="members">members</option>
                <option value="curators">curators</option>
              </select>
            </label>
            <label className="flex items-center justify-between gap-3 text-sm">
              {t("k_default_editor_policy")}
              <select value={settings.default_editor_policy} onChange={(e) => setSettings({ ...settings, default_editor_policy: e.target.value as DeckSettings["default_editor_policy"] })} className="border border-rule bg-transparent px-1">
                <option value="any_member">any_member</option>
                <option value="curators">curators</option>
                <option value="maker_list">maker_list</option>
              </select>
            </label>
            {bool("allow_branches")}
            {bool("allow_forks")}
            {bool("allow_guest_readers")}
            <button type="button" className="self-start bg-ink text-paper px-4 py-2 text-sm" onClick={() => save({ settings })}>
              {t("save")}
            </button>
          </>
        )}
        {section === "measurement" && (
          <>
            {num("ready_threshold", 1, 1, 50)}
            {num("max_edits_per_card", 1, 1, 20)}
            {num("fidelity_threshold", 0.01, 0, 1)}
            {num("style_threshold", 0.01, 0, 1)}
            <button type="button" className="self-start bg-ink text-paper px-4 py-2 text-sm" onClick={() => save({ settings })}>
              {t("save")}
            </button>
          </>
        )}
        {section === "generation" && (
          <>
            {num("candidates_per_generation", 1, 1, 4)}
            {num("generation_quota_month", 10, 0, 100000)}
            {bool("live_generation_in_sessions")}
            <label className="flex items-center justify-between gap-3 text-sm">
              {t("provider")}
              <select value={settings.provider ?? ""} onChange={(e) => setSettings({ ...settings, provider: e.target.value || null })} className="border border-rule bg-transparent px-1">
                <option value="">default</option>
                {["local", "gemini", "flux", "openai"].map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="self-start bg-ink text-paper px-4 py-2 text-sm" onClick={() => save({ settings })}>
              {t("save")}
            </button>
          </>
        )}
        {section === "export" && (
          <>
            <p className="text-sm text-muted">{t("exportHint")}</p>
            <button type="button" className="self-start border border-ink px-4 py-2 text-sm" onClick={() => v5.decks.exportZip(deck.id).then((j) => setExportJob(j.id)).catch((e) => setMsg(String(e)))}>
              {t("exportZip")}
            </button>
            {exportJob && <p className="text-xs text-muted">job {exportJob}</p>}
          </>
        )}
        {section === "danger" && (
          <>
            <p className="text-sm text-accent">{t("dangerHint")}</p>
            <button
              type="button"
              className="self-start border border-accent text-accent px-4 py-2 text-sm"
              onClick={() => {
                if (window.confirm(t("confirmDelete"))) v5.decks.remove(deck.id).then(() => router.push("/"));
              }}
            >
              {t("delete")}
            </button>
          </>
        )}
        {msg && <p className="text-xs text-muted">{msg}</p>}
      </div>
    </div>
  );
}

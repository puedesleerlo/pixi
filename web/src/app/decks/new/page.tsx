"use client";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import ErrorState from "@/components/ErrorState";
import JobProgress from "@/components/JobProgress";
import { imageSrc, v5 } from "@/lib/api";
import { useLoad, useMe } from "@/lib/hooks";
import type { BaseDeck, Deck, DeckRole, DeckWizardPayload, StyleGuide, Symbol, Visibility } from "@/lib/types";

const STRUCTURES = ["tarot78", "majors22", "minors56", "lenormand36", "mantegna50", "free"];
const LINES: StyleGuide["line"][] = ["ink", "woodcut", "painted", "flat", "photo", "custom"];

function Wizard() {
  const t = useTranslations("wizard");
  const router = useRouter();
  const sp = useSearchParams();
  const { data: me, loading: meLoading } = useMe();
  const bases = useLoad(() => v5.baseDecks.list(), []);
  const publicDecks = useLoad(() => v5.decks.list({ visibility: "public" }), []);
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("private");
  const [kind, setKind] = useState<"blank" | "base" | "fork">(sp.get("base") ? "base" : "blank");
  const [baseSlug, setBaseSlug] = useState(sp.get("base") ?? "");
  const [forkId, setForkId] = useState("");
  const [structure, setStructure] = useState("tarot78");
  const [styleMode, setStyleMode] = useState<"base" | "describe" | "upload">(sp.get("base") ? "base" : "describe");
  const [style, setStyle] = useState<Partial<StyleGuide>>({ prompt_prefix: "", line: "ink", palette: ["#f4efe6", "#141414"], border: { style: "thin", color: "#141414" }, aspect: "2.75x4.75", reference_images: [] });
  const [previewJob, setPreviewJob] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [registry, setRegistry] = useState<Symbol[]>([]);
  const [importKeys, setImportKeys] = useState<Set<string>>(new Set());
  const [cardMode, setCardMode] = useState<"inherit" | "reference">("inherit");
  const [invites, setInvites] = useState<{ email: string; role: DeckRole }[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const base: BaseDeck | undefined = useMemo(() => bases.data?.find((b) => b.slug === baseSlug), [bases.data, baseSlug]);
  useEffect(() => {
    if (base) setStructure(base.structure_template_id || "tarot78");
  }, [base]);
  useEffect(() => {
    if (kind === "base" && baseSlug) {
      v5.baseDecks
        .symbols(baseSlug)
        .then((s) => {
          setRegistry(s);
          setImportKeys(new Set(s.map((x) => x.key)));
        })
        .catch(() => setRegistry([]));
    } else {
      setRegistry([]);
      setImportKeys(new Set());
    }
  }, [kind, baseSlug]);

  const canNext = [name.trim().length > 0, kind === "blank" || (kind === "base" && !!baseSlug) || (kind === "fork" && !!forkId), !!structure, true, true][step];

  async function preview() {
    setPreviewErr(null);
    setPreviewUrl(null);
    try {
      const r = await v5.decks.previewStyle(styleMode === "base" && base ? { style_from_base_deck_id: base.id } : { style_guide: style });
      if (r.image_url) setPreviewUrl(r.image_url);
      else if (r.job_id) setPreviewJob(r.job_id);
    } catch (e) {
      setPreviewErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function create() {
    setBusy(true);
    setErr(null);
    const payload: DeckWizardPayload = {
      name: name.trim(),
      description,
      visibility,
      origin: kind === "base" ? { kind, base_deck_id: base?.id ?? baseSlug } : kind === "fork" ? { kind, forked_from_deck_id: forkId } : { kind },
      structure_template_id: structure,
      ...(styleMode === "base" && base ? { style_from_base_deck_id: base.id } : { style_guide: style }),
      import_symbols: kind === "base" ? [...importKeys] : [],
      card_mode: cardMode,
      invites,
    };
    try {
      const d: Deck = await v5.decks.create(payload);
      router.push(`/d/${d.slug}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  if (!meLoading && (!me || me.is_guest)) return <div className="max-w-2xl mx-auto px-4"><ErrorState error={null} status={401} /></div>;
  const steps = [t("s1"), t("s2"), t("s3"), t("s4"), t("s5")];
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 flex flex-col gap-6">
      <h1 className="font-display text-3xl">{t("title")}</h1>
      <ol className="flex flex-wrap gap-2 text-xs">
        {steps.map((s, i) => (
          <li key={s} className={`border px-2 py-1 ${i === step ? "border-ink bg-ink text-paper" : i < step ? "border-ink" : "border-rule text-muted"}`}>
            {i + 1} · {s}
          </li>
        ))}
      </ol>

      {step === 0 && (
        <section className="flex flex-col gap-3">
          <label className="text-xs flex flex-col gap-1">
            {t("name")}
            <input value={name} onChange={(e) => setName(e.target.value.slice(0, 60))} className="border border-ink px-3 py-2 text-base" autoFocus />
          </label>
          <label className="text-xs flex flex-col gap-1">
            {t("description")}
            <textarea value={description} onChange={(e) => setDescription(e.target.value.slice(0, 500))} rows={2} className="border border-rule px-3 py-2 text-sm" />
          </label>
          <div className="text-xs">{t("visibility")}</div>
          <div className="flex gap-2 text-sm">
            {(["private", "unlisted", "public"] as Visibility[]).map((v) => (
              <button key={v} type="button" onClick={() => setVisibility(v)} className={`border px-3 py-1.5 ${visibility === v ? "border-ink bg-ink text-paper" : "border-rule"}`}>
                {t(`vis_${v}`)}
              </button>
            ))}
          </div>
        </section>
      )}

      {step === 1 && (
        <section className="flex flex-col gap-3">
          <div className="grid sm:grid-cols-3 gap-2 text-sm">
            {(["blank", "base", "fork"] as const).map((k) => (
              <button key={k} type="button" onClick={() => setKind(k)} className={`border p-3 text-left ${kind === k ? "border-ink bg-ink text-paper" : "border-rule"}`}>
                <div className="font-display text-base">{t(`from_${k}`)}</div>
                <div className={`text-xs ${kind === k ? "text-paper/80" : "text-muted"}`}>{t(`from_${k}_hint`)}</div>
              </button>
            ))}
          </div>
          {kind === "base" && (
            <div className="grid sm:grid-cols-2 gap-2">
              {bases.data?.map((b) => (
                <button key={b.slug} type="button" onClick={() => setBaseSlug(b.slug)} disabled={b.status === "planned"} className={`border p-2 text-left text-sm ${baseSlug === b.slug ? "border-accent outline outline-1 outline-accent" : "border-rule"}`}>
                  <div>{b.name}</div>
                  <div className="text-xs text-muted">
                    {b.year} · {b.card_count} {t("cards")} · {b.status}
                  </div>
                </button>
              ))}
            </div>
          )}
          {kind === "base" && baseSlug && (
            <div className="flex gap-2 text-sm">
              {(["inherit", "reference"] as const).map((m) => (
                <button key={m} type="button" onClick={() => setCardMode(m)} className={`border px-3 py-1.5 ${cardMode === m ? "border-ink bg-ink text-paper" : "border-rule"}`}>
                  {t(`mode_${m}`)}
                </button>
              ))}
            </div>
          )}
          {kind === "fork" && (
            <select value={forkId} onChange={(e) => setForkId(e.target.value)} className="border border-rule px-2 py-2 text-sm bg-transparent">
              <option value="">{t("pickDeck")}</option>
              {publicDecks.data?.filter((d) => d.settings?.allow_forks !== false).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          )}
        </section>
      )}

      {step === 2 && (
        <section className="grid sm:grid-cols-3 gap-2 text-sm">
          {STRUCTURES.map((s) => (
            <button key={s} type="button" onClick={() => setStructure(s)} className={`border p-3 text-left ${structure === s ? "border-ink bg-ink text-paper" : "border-rule"}`}>
              <div className="font-display">{s}</div>
              <div className={`text-xs ${structure === s ? "text-paper/80" : "text-muted"}`}>{t(`struct_${s}`)}</div>
            </button>
          ))}
        </section>
      )}

      {step === 3 && (
        <section className="flex flex-col gap-3 text-sm">
          <div className="flex gap-2">
            {(["base", "describe", "upload"] as const).map((m) => (
              <button key={m} type="button" onClick={() => setStyleMode(m)} disabled={m === "base" && !base} className={`border px-3 py-1.5 ${styleMode === m ? "border-ink bg-ink text-paper" : "border-rule"}`}>
                {t(`style_${m}`)}
              </button>
            ))}
          </div>
          {styleMode === "base" && base && <p className="text-muted text-xs">{t("styleFromBaseHint", { name: base.name })}</p>}
          {styleMode !== "base" && (
            <>
              <label className="text-xs flex flex-col gap-1">
                {t("promptPrefix")}
                <textarea value={style.prompt_prefix ?? ""} onChange={(e) => setStyle({ ...style, prompt_prefix: e.target.value.slice(0, 400) })} rows={2} className="border border-ink px-3 py-2 text-sm" placeholder="black ink line art on cream paper, single figure…" />
              </label>
              <div className="flex flex-wrap gap-2 items-center text-xs">
                {t("line")}
                {LINES.map((l) => (
                  <button key={l} type="button" onClick={() => setStyle({ ...style, line: l })} className={`border px-2 py-1 ${style.line === l ? "border-ink bg-ink text-paper" : "border-rule"}`}>
                    {l}
                  </button>
                ))}
              </div>
              <div className="flex gap-2 items-center text-xs">
                {t("palette")}
                {(style.palette ?? []).map((c, i) => (
                  <input key={i} type="color" value={c} onChange={(e) => setStyle({ ...style, palette: (style.palette ?? []).map((x, j) => (j === i ? e.target.value : x)) })} />
                ))}
                <button type="button" className="underline" onClick={() => setStyle({ ...style, palette: [...(style.palette ?? []), "#888888"] })}>
                  +
                </button>
              </div>
              {styleMode === "upload" && (
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  className="text-xs"
                  onChange={(e) => {
                    const files = Array.from(e.target.files ?? []).slice(0, 5);
                    Promise.all(
                      files.map(
                        (f) =>
                          new Promise<string>((res) => {
                            const r = new FileReader();
                            r.onload = () => res(String(r.result));
                            r.readAsDataURL(f);
                          }),
                      ),
                    ).then((urls) => setStyle({ ...style, reference_images: urls.map((url) => ({ url, source: "upload" as const, weight: 1 })) }));
                  }}
                />
              )}
            </>
          )}
          <div className="flex items-center gap-3">
            <button type="button" onClick={preview} className="border border-ink px-3 py-1.5">
              {t("previewCard")}
            </button>
            <span className="text-xs text-muted">{t("previewHint")}</span>
          </div>
          {previewJob && !previewUrl && (
            <JobProgress
              jobId={previewJob}
              onDone={(j) => {
                const r = j.result as { image_url?: string } | undefined;
                if (r?.image_url) setPreviewUrl(r.image_url);
                setPreviewJob(null);
              }}
            />
          )}
          {previewErr && <p className="text-xs text-muted">{t("previewUnavailable")}</p>}
          <div className="w-40 aspect-[11/19] border border-rule bg-[#faf6ee] flex items-center justify-center overflow-hidden">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {previewUrl ? <img src={imageSrc(previewUrl) ?? previewUrl} alt="" className="w-full h-full object-cover" /> : <span className="text-[10px] text-muted px-2 text-center">{t("previewPlaceholder")}</span>}
          </div>
        </section>
      )}

      {step === 4 && (
        <section className="flex flex-col gap-4 text-sm">
          {kind === "base" && (
            <div>
              <div className="flex items-baseline justify-between">
                <div className="text-xs uppercase tracking-widest text-muted">{t("importSymbols")}</div>
                <div className="text-xs">
                  <button type="button" className="underline mr-2" onClick={() => setImportKeys(new Set(registry.map((s) => s.key)))}>
                    {t("all")}
                  </button>
                  <button type="button" className="underline" onClick={() => setImportKeys(new Set())}>
                    {t("none")}
                  </button>
                </div>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-1 mt-2 max-h-64 overflow-auto border border-rule p-2">
                {registry.map((s) => (
                  <label key={s.key} className="flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      checked={importKeys.has(s.key)}
                      onChange={(e) => {
                        const n = new Set(importKeys);
                        if (e.target.checked) n.add(s.key);
                        else n.delete(s.key);
                        setImportKeys(n);
                      }}
                    />
                    {s.name}
                  </label>
                ))}
                {registry.length === 0 && <span className="text-muted text-xs">{t("noRegistry")}</span>}
              </div>
            </div>
          )}
          <div>
            <div className="text-xs uppercase tracking-widest text-muted">{t("invite")}</div>
            <div className="flex gap-2 mt-1">
              <input type="email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} className="border border-rule px-2 py-1.5 flex-1" placeholder="email" />
              <button
                type="button"
                className="border border-ink px-3"
                onClick={() => {
                  if (inviteEmail.includes("@")) setInvites([...invites, { email: inviteEmail, role: "member" }]);
                  setInviteEmail("");
                }}
              >
                +
              </button>
            </div>
            <ul className="text-xs mt-1 flex flex-col gap-1">
              {invites.map((i, k) => (
                <li key={k} className="flex gap-2 items-center">
                  {i.email}
                  <select value={i.role} onChange={(e) => setInvites(invites.map((x, j) => (j === k ? { ...x, role: e.target.value as DeckRole } : x)))} className="border border-rule bg-transparent">
                    <option value="member">member</option>
                    <option value="curator">curator</option>
                  </select>
                  <button type="button" className="underline" onClick={() => setInvites(invites.filter((_, j) => j !== k))}>
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {err && <p className="text-sm text-accent">{err}</p>}
      <div className="flex justify-between">
        <button type="button" disabled={step === 0} onClick={() => setStep(step - 1)} className="border border-rule px-4 py-2 text-sm">
          {t("back")}
        </button>
        {step < 4 ? (
          <button type="button" disabled={!canNext} onClick={() => setStep(step + 1)} className="bg-ink text-paper px-4 py-2 text-sm">
            {t("next")}
          </button>
        ) : (
          <button type="button" disabled={busy} onClick={create} className="bg-ink text-paper px-4 py-2 text-sm">
            {busy ? "…" : t("create")}
          </button>
        )}
      </div>
    </div>
  );
}

export default function NewDeckPage() {
  return (
    <Suspense fallback={null}>
      <Wizard />
    </Suspense>
  );
}

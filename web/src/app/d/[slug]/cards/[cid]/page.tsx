"use client";
import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import ErrorState from "@/components/ErrorState";
import JobProgress from "@/components/JobProgress";
import MiniBars from "@/components/MiniBars";
import Share from "@/components/Share";
import Sliders8 from "@/components/Sliders8";
import StatusChip from "@/components/StatusChip";
import { useDeckCtx } from "@/components/ws/DeckContext";
import { AXES } from "@/lib/axes";
import { ApiError, imageSrc, v5 } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { Axes8, Card, EditOp, Job, Symbol, SymbolPlacement, Version } from "@/lib/types";

const TABS = ["view", "generate", "edit", "versions", "readings", "access"] as const;
type Tab = (typeof TABS)[number];
const OPS: EditOp[] = ["add", "remove", "replace", "emphasize", "deemphasize", "reposition", "cosmetic"];
const PLACEMENTS: SymbolPlacement[] = ["any", "center", "top", "bottom", "left", "right"];

function Studio() {
  const t = useTranslations("studio");
  const { deck, me, atLeast, role } = useDeckCtx();
  const { cid } = useParams<{ cid: string }>();
  const sp = useSearchParams();
  const router = useRouter();
  const tab = (TABS.includes(sp.get("tab") as Tab) ? sp.get("tab") : "view") as Tab;
  const card = useLoad(() => v5.cards.get(cid), [cid]);
  const versions = useLoad(() => v5.cards.versions(cid).catch(() => [] as Version[]), [cid]);
  const symbols = useLoad(() => v5.symbols.list(deck.id, "active"), [deck.id]);
  const c = card.data;
  const cur = useMemo(() => c?.current_version ?? versions.data?.find((v) => v.id === c?.current_version_id) ?? null, [c, versions.data]);
  const symById = useMemo(() => new Map((symbols.data ?? []).map((s) => [s.id, s])), [symbols.data]);
  const isMaker = !!me && !!c && c.maker_id === me.id;
  const isApprovedEditor = !!me && !!c && (c.approved_editors === "*" ? atLeast("member") : c.approved_editors.includes(me.id) || (deck.settings?.default_editor_policy === "curators" && atLeast("curator")));
  const setTab = (k: Tab) => router.replace(`/d/${deck.slug}/cards/${cid}?tab=${k}`);
  if (card.error) return <ErrorState error={card.error} status={card.status} />;
  if (!c) return <p className="text-sm text-muted">…</p>;
  const position = deck.structure?.positions?.find((p) => p.key === c.position_key);
  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-baseline gap-3">
        <Link href={`/d/${deck.slug}/cards`} className="text-xs text-muted underline">
          ← {t("allCards")}
        </Link>
        <h1 className="font-display text-2xl">{c.title ?? position?.title ?? c.position_key}</h1>
        <span className="text-xs text-muted">{c.position_key}</span>
        <StatusChip value={c.status} />
        {c.verdict?.verdict && <StatusChip value={c.verdict.verdict} />}
        <span className="text-xs text-muted">
          {t("maker")}: {c.maker_name ?? c.maker_id}
        </span>
      </header>
      <div className="flex flex-wrap gap-1 text-sm border-b border-rule">
        {TABS.filter((k) => k !== "access" || isMaker || atLeast("curator")).map((k) => (
          <button key={k} type="button" onClick={() => setTab(k)} className={`px-3 py-1.5 -mb-px border-b-2 ${tab === k ? "border-ink" : "border-transparent text-muted"}`}>
            {t(`tab_${k}`)}
          </button>
        ))}
      </div>
      {tab === "view" && <ViewTab card={c} cur={cur} symById={symById} isMaker={isMaker} isEditor={isApprovedEditor} refresh={card.refresh} setTab={setTab} />}
      {tab === "generate" && <GenerateTab card={c} cur={cur} symbols={symbols.data ?? []} refresh={() => (card.refresh(), versions.refresh())} />}
      {tab === "edit" && <EditTab card={c} cur={cur} symbols={symbols.data ?? []} symById={symById} canEdit={isApprovedEditor} refresh={() => (card.refresh(), versions.refresh())} />}
      {tab === "versions" && <VersionsTab card={c} versions={versions.data ?? []} symById={symById} refresh={() => (card.refresh(), versions.refresh())} />}
      {tab === "readings" && <ReadingsTab cur={cur} ready={deck.settings?.ready_threshold ?? 3} />}
      {tab === "access" && (isMaker || atLeast("curator")) && <AccessTab card={c} isMaker={isMaker} refresh={card.refresh} />}
      <p className="text-[10px] text-muted">
        {t("yourRole")}: {role}
        {isMaker && ` · ${t("youAreMaker")}`}
        {isApprovedEditor && !isMaker && ` · ${t("youMayEdit")}`}
      </p>
    </div>
  );
}

function SymbolList({ ids, symById, salience }: { ids: string[]; symById: Map<string, Symbol>; salience?: Map<string, number> }) {
  return (
    <div className="flex flex-wrap gap-1">
      {ids.map((id) => (
        <span key={id} className="text-[11px] border border-rule px-1.5 py-0.5">
          {symById.get(id)?.name ?? id}
          {salience?.has(id) && <span className="text-muted"> {salience.get(id)!.toFixed(1)}</span>}
        </span>
      ))}
      {ids.length === 0 && <span className="text-[11px] text-muted">—</span>}
    </div>
  );
}

function ViewTab({ card, cur, symById, isMaker, isEditor, refresh, setTab }: { card: Card; cur: Version | null; symById: Map<string, Symbol>; isMaker: boolean; isEditor: boolean; refresh: () => void; setTab: (k: Tab) => void }) {
  const t = useTranslations("studio");
  const { deck, atLeast } = useDeckCtx();
  const [showIntent, setShowIntent] = useState(false);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const detected = new Map((cur?.symbols_detected ?? []).map((d) => [d.symbol_id, d.salience]));
  const missing = cur?.checks?.symbols_missing ?? [];
  const src = imageSrc(cur?.image_url);
  return (
    <div className="grid md:grid-cols-[minmax(0,320px)_1fr] gap-6">
      <div>
        <div className="aspect-[11/19] border border-ink bg-[#faf6ee] flex items-center justify-center overflow-hidden">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {src ? <img src={src} alt="" className="w-full h-full object-contain" /> : <span className="text-xs text-muted text-center px-4">{t("noImage")}</span>}
        </div>
        {cur && (
          <div className="text-[11px] text-muted mt-1">
            v{cur.v} · {cur.branch_key} · {cur.how?.provider ?? ""} {cur.checks?.style_score != null && `· style ${cur.checks.style_score.toFixed(2)}`}
            {cur.checks?.fidelity != null && ` · fidelity ${cur.checks.fidelity.toFixed(2)}`}
          </div>
        )}
      </div>
      <div className="flex flex-col gap-4 text-sm">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-muted">{t("symbolsDeclared")}</div>
          <SymbolList ids={(cur?.symbols_declared ?? []).map((s) => s.symbol_id)} symById={symById} />
          <div className="text-[10px] uppercase tracking-widest text-muted mt-2">{t("symbolsDetected")}</div>
          <SymbolList ids={[...detected.keys()]} symById={symById} salience={detected} />
          {missing.length > 0 && (
            <p className="text-xs text-accent mt-1">
              {t("notRendered")}: {missing.map((m) => symById.get(m)?.name ?? m).join(", ")}
            </p>
          )}
        </div>
        <div className="flex gap-4 text-xs">
          <span>
            {t("verdict")}: <b>{card.verdict?.verdict ?? "collecting"}</b> {card.verdict?.verdict === "collecting" && `· ${card.verdict?.n ?? cur?.n_readings ?? 0}/${card.verdict?.needed ?? deck.settings?.ready_threshold ?? 8}`}
          </span>
          <span>
            {t("fidelity")}: <b>{card.fidelity != null ? card.fidelity.toFixed(2) : "—"}</b>
          </span>
          <span>
            {t("readings")}: <b>{card.n_readings ?? cur?.n_readings ?? 0}</b>
          </span>
        </div>
        {card.intent && (
          <div className="border border-rule p-3">
            <div className="flex items-center justify-between">
              <div className="text-[10px] uppercase tracking-widest text-muted">{t("intentPrivate")}</div>
              {isMaker && (
                <button type="button" className="text-xs underline" onClick={() => setShowIntent((s) => !s)}>
                  {showIntent ? t("blur") : t("reveal")}
                </button>
              )}
            </div>
            <div className={isMaker && !showIntent ? "blur-sm select-none" : ""}>
              <p className="font-display text-lg">“{card.intent.statement}”</p>
              <MiniBars axes={card.intent.axes} width={220} labels />
            </div>
          </div>
        )}
        <div className="flex flex-wrap gap-2 text-xs">
          <Link href={`/d/${deck.slug}/read`} className="border border-ink px-3 py-1.5">
            {t("readThisCard")}
          </Link>
          {isEditor && (card.status === "open" || (atLeast("curator") && deck.settings?.allow_branches)) && (
            <button type="button" className="bg-ink text-paper px-3 py-1.5" onClick={() => setTab("edit")}>
              {t("edit")}
            </button>
          )}
          {!isEditor && !isMaker && atLeast("member") && (
            <span className="flex gap-1 items-center">
              <input value={note} onChange={(e) => setNote(e.target.value.slice(0, 140))} placeholder={t("requestNote")} className="border border-rule px-2 py-1" />
              <button type="button" className="border border-ink px-2 py-1" onClick={() => v5.cards.requestEdit(card.id, note).then(() => (setMsg(t("requested")), refresh()))}>
                {t("requestToEdit")}
              </button>
            </span>
          )}
          {(isMaker || atLeast("curator")) && card.status !== "archived" && (
            <button type="button" className="border border-rule px-3 py-1.5" onClick={() => window.confirm(t("confirmArchive")) && v5.cards.archive(card.id).then(refresh)}>
              {t("archive")}
            </button>
          )}
        </div>
        {msg && <p className="text-xs text-muted">{msg}</p>}
        <details className="text-xs">
          <summary className="cursor-pointer">{t("share")}</summary>
          <Share path={`/d/${deck.slug}/cards/${card.id}`} token={card.share_token} />
        </details>
      </div>
    </div>
  );
}

function Candidates({ job, kind, onChoose, threshold }: { job: Job; kind: "generate" | "edit"; onChoose: (i: number) => void; threshold: number }) {
  const t = useTranslations("studio");
  const r = (job.result ?? {}) as { candidates?: { image_url: string; style_score?: number; fidelity?: number; containment?: number; heatmap_url?: string; symbols_missing?: string[] }[]; version_id?: string; retries?: number };
  return (
    <div className="flex flex-col gap-2">
      <div className="text-[10px] uppercase tracking-widest text-muted">
        {t("candidates")} {r.retries ? `· ${t("retries")} ${r.retries}` : ""}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {(r.candidates ?? []).map((cand, i) => {
          const low = kind === "edit" && cand.fidelity != null && cand.fidelity < threshold;
          return (
            <div key={i} className={`border ${low ? "border-rule opacity-60" : "border-ink"} flex flex-col`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={imageSrc(cand.image_url) ?? ""} alt="" className="w-full aspect-[11/19] object-cover" />
              <div className="text-[10px] p-1 flex flex-col gap-0.5">
                {cand.style_score != null && <span>style {cand.style_score.toFixed(2)}</span>}
                {cand.fidelity != null && <span className={low ? "text-accent" : ""}>fidelity {cand.fidelity.toFixed(2)}</span>}
                {cand.containment != null && <span>containment {cand.containment.toFixed(2)}</span>}
                {low && <span className="text-accent">{t("changedMore")}</span>}
                {cand.symbols_missing?.length ? <span className="text-accent">{t("missing")}: {cand.symbols_missing.join(", ")}</span> : null}
              </div>
              <button type="button" className="bg-ink text-paper text-xs py-1" onClick={() => onChoose(i)}>
                {t("choose")}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GenerateTab({ card, cur, symbols, refresh }: { card: Card; cur: Version | null; symbols: Symbol[]; refresh: () => void }) {
  const t = useTranslations("studio");
  const { deck, atLeast } = useDeckCtx();
  const [mode, setMode] = useState<"prompt" | "reference" | "variation" | "upload">("prompt");
  const [prompt, setPrompt] = useState("");
  const [refUrl, setRefUrl] = useState("");
  const [strength, setStrength] = useState(0.55);
  const [sel, setSel] = useState<Set<string>>(new Set((cur?.symbols_declared ?? []).map((s) => s.symbol_id)));
  const [placements, setPlacements] = useState<Record<string, SymbolPlacement | "">>({});
  const [statement, setStatement] = useState(card.intent?.statement ?? "");
  const [axes, setAxes] = useState<Axes8>(card.intent?.axes ?? Array(8).fill(0));
  const [n, setN] = useState(deck.settings?.candidates_per_generation ?? 2);
  const [upload, setUpload] = useState<string | null>(null);
  const [rights, setRights] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [title, setTitle] = useState(card.title ?? "");
  const allowed = card.status === "draft" || atLeast("curator");
  async function go() {
    setErr(null);
    setJob(null);
    try {
      if (statement.trim()) await v5.cards.update(card.id, { title: title || undefined, intent: { statement: statement.trim().slice(0, 140), axes } });
      const j = await v5.cards.generate(card.id, {
        mode,
        prompt_user: prompt,
        reference_image_url: mode === "reference" ? refUrl : undefined,
        strength: mode === "reference" ? strength : undefined,
        upload_data_url: mode === "upload" ? upload : undefined,
        rights_attested: mode === "upload" ? rights : undefined,
        symbols: [...sel].map((id) => ({ symbol_id: id, placement: placements[id] || undefined })),
        n,
      });
      setJobId(j.id);
    } catch (e) {
      setErr(e instanceof ApiError && e.status === 404 ? t("notAvailableYet") : e instanceof Error ? e.message : String(e));
    }
  }
  return (
    <div className="flex flex-col gap-4 text-sm max-w-2xl">
      {!allowed && <p className="text-xs text-muted">{t("generateOnlyDraft")}</p>}
      <div className="flex flex-wrap gap-2">
        {(["prompt", "reference", "variation", "upload"] as const).map((m) => (
          <button key={m} type="button" onClick={() => setMode(m)} disabled={m === "variation" && !cur} className={`border px-3 py-1 ${mode === m ? "border-ink bg-ink text-paper" : "border-rule"}`}>
            {t(`mode_${m}`)}
          </button>
        ))}
      </div>
      <div className="border border-rule bg-[#faf6ee] px-3 py-2 text-xs text-muted">
        <span className="uppercase tracking-widest">{t("stylePrefix")}</span> · {deck.style_guide?.prompt_prefix || "—"}
      </div>
      {mode === "prompt" && <textarea value={prompt} onChange={(e) => setPrompt(e.target.value.slice(0, 600))} rows={3} className="border border-ink px-3 py-2" placeholder={t("promptPlaceholder")} />}
      {mode === "reference" && (
        <div className="flex flex-col gap-2">
          <input value={refUrl} onChange={(e) => setRefUrl(e.target.value)} className="border border-ink px-3 py-2" placeholder={t("referencePlaceholder")} />
          {deck.origin?.base_deck_id && (
            <Link href={`/base/${deck.origin.base_deck_id}`} className="text-xs underline">
              {t("browseBaseCards")}
            </Link>
          )}
          <label className="text-xs flex items-center gap-2">
            {t("strength")} <input type="range" min={0.3} max={0.8} step={0.05} value={strength} onChange={(e) => setStrength(Number(e.target.value))} /> {strength.toFixed(2)}
          </label>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value.slice(0, 600))} rows={2} className="border border-rule px-3 py-2" placeholder={t("promptPlaceholder")} />
        </div>
      )}
      {mode === "upload" && (
        <div className="flex flex-col gap-2 text-xs">
          <input
            type="file"
            accept="image/*"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const r = new FileReader();
              r.onload = () => setUpload(String(r.result));
              r.readAsDataURL(f);
            }}
          />
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} /> {t("rightsAttest")}
          </label>
        </div>
      )}
      <div>
        <div className="text-[10px] uppercase tracking-widest text-muted mb-1">{t("symbolsAtLeastOne")}</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-1 max-h-56 overflow-auto border border-rule p-2 text-xs">
          {symbols.map((s) => (
            <div key={s.id} className="flex items-center gap-1">
              <label className="flex items-center gap-1 flex-1 min-w-0">
                <input
                  type="checkbox"
                  checked={sel.has(s.id)}
                  onChange={(e) => {
                    const nx = new Set(sel);
                    if (e.target.checked) nx.add(s.id);
                    else nx.delete(s.id);
                    setSel(nx);
                  }}
                />
                <span className="truncate" title={s.gloss}>
                  {s.name}
                </span>
              </label>
              {sel.has(s.id) && (
                <select value={placements[s.id] ?? ""} onChange={(e) => setPlacements({ ...placements, [s.id]: e.target.value as SymbolPlacement | "" })} className="border border-rule bg-transparent text-[10px]">
                  <option value="">{s.placement}</option>
                  {PLACEMENTS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              )}
            </div>
          ))}
        </div>
        <Link href={`/d/${deck.slug}/symbols`} className="text-xs underline">
          {t("needsSymbol")}
        </Link>
      </div>
      <div className="border border-rule p-3 flex flex-col gap-2">
        <div className="text-[10px] uppercase tracking-widest text-muted">{t("intentPrivate")}</div>
        <input value={title} onChange={(e) => setTitle(e.target.value.slice(0, 60))} className="border border-rule px-2 py-1 text-sm" placeholder={t("titleOptional")} />
        <textarea value={statement} onChange={(e) => setStatement(e.target.value.slice(0, 140))} rows={2} className="border border-ink px-2 py-1.5" placeholder={t("intentPlaceholder")} />
        <Sliders8 value={axes} onChange={setAxes} />
      </div>
      <label className="text-xs flex items-center gap-2">
        {t("candidates")} <input type="number" min={1} max={4} value={n} onChange={(e) => setN(Math.max(1, Math.min(4, Number(e.target.value))))} className="border border-rule w-16 px-1" />
      </label>
      <button type="button" disabled={!allowed || sel.size === 0 || !statement.trim() || (mode === "upload" && (!upload || !rights))} onClick={go} className="self-start bg-ink text-paper px-4 py-2">
        {t("generate")}
      </button>
      {err && <p className="text-xs text-accent">{err}</p>}
      {jobId && !job && <JobProgress jobId={jobId} onDone={setJob} />}
      {job?.status === "done" && (
        <Candidates
          job={job}
          kind="generate"
          threshold={0}
          onChoose={(i) => {
            const vid = (job.result as { version_id?: string })?.version_id;
            (vid ? v5.versions.choose(vid, i) : Promise.reject(new Error("no version"))).then(() => (setJob(null), setJobId(null), refresh())).catch((e) => setErr(String(e)));
          }}
        />
      )}
      {job?.status === "failed" && <p className="text-xs text-accent">{job.error}</p>}
    </div>
  );
}

function EditTab({ card, cur, symbols, symById, canEdit, refresh }: { card: Card; cur: Version | null; symbols: Symbol[]; symById: Map<string, Symbol>; canEdit: boolean; refresh: () => void }) {
  const t = useTranslations("studio");
  const { deck } = useDeckCtx();
  const [op, setOp] = useState<EditOp>("add");
  const [symbolId, setSymbolId] = useState("");
  const [toSymbolId, setToSymbolId] = useState("");
  const [placement, setPlacement] = useState<SymbolPlacement | "">("");
  const [how, setHow] = useState("");
  const [rationale, setRationale] = useState("");
  const [bet, setBet] = useState<number | null>(null);
  const [n, setN] = useState(deck.settings?.candidates_per_generation ?? 2);
  const [gaps, setGaps] = useState<number[] | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!cur) return;
    v5.versions
      .reveal(cur.id)
      .then((r) => {
        const g = (r as { gaps_signed?: number[]; gaps?: number[] }).gaps_signed ?? (r as { gaps?: number[] }).gaps;
        if (Array.isArray(g) && g.length === 8) setGaps(g);
      })
      .catch(() => {});
  }, [cur]);
  const onCard = (cur?.symbols_detected?.map((d) => d.symbol_id) ?? []).concat((cur?.symbols_declared ?? []).map((s) => s.symbol_id)).filter((v, i, a) => a.indexOf(v) === i);
  const experiment = op !== "cosmetic";
  const topGaps = gaps ? [...gaps.keys()].sort((a, b) => Math.abs(gaps[b]) - Math.abs(gaps[a])).slice(0, 3) : [];
  const complete = rationale.trim().length > 0 && (!experiment || bet !== null) && (op === "cosmetic" ? how.trim().length > 0 : symbolId !== "") && (op !== "replace" || toSymbolId !== "");
  async function go() {
    setErr(null);
    setJob(null);
    try {
      const j = await v5.cards.edit(card.id, {
        base_version_id: cur?.id,
        op,
        symbol_id: op === "cosmetic" ? undefined : symbolId,
        to_symbol_id: op === "replace" ? toSymbolId : undefined,
        placement: placement || undefined,
        prompt_user: how || undefined,
        rationale: rationale.trim().slice(0, 140),
        bet_axis: experiment ? bet : undefined,
        n,
      });
      setJobId(j.id);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setErr(t("versionStale"));
        refresh();
      } else setErr(e instanceof ApiError && e.status === 404 ? t("notAvailableYet") : e instanceof Error ? e.message : String(e));
    }
  }
  if (!cur) return <p className="text-sm text-muted">{t("noVersionYet")}</p>;
  if (!canEdit) return <p className="text-sm text-muted">{t("notApproved")}</p>;
  return (
    <div className="flex flex-col gap-4 text-sm max-w-2xl">
      {card.status !== "open" && <p className="text-xs text-accent">{t("cardNotOpen", { status: card.status })}</p>}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-1">
        {OPS.map((o) => (
          <button key={o} type="button" onClick={() => setOp(o)} className={`border px-2 py-1.5 text-left ${op === o ? "border-ink bg-ink text-paper" : "border-rule"}`}>
            <div>{t(`op_${o}`)}</div>
            <div className={`text-[10px] ${op === o ? "text-paper/80" : "text-muted"}`}>{o === "cosmetic" ? t("notExperiment") : t("experiment")}</div>
          </button>
        ))}
      </div>
      {op !== "cosmetic" && (
        <div className="flex flex-wrap gap-2 items-center">
          <select value={symbolId} onChange={(e) => setSymbolId(e.target.value)} className="border border-ink px-2 py-1.5 bg-transparent">
            <option value="">{op === "add" ? t("pickSymbolToAdd") : t("pickSymbolOnCard")}</option>
            {(op === "add" ? symbols : symbols.filter((s) => onCard.includes(s.id))).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          {op === "replace" && (
            <select value={toSymbolId} onChange={(e) => setToSymbolId(e.target.value)} className="border border-ink px-2 py-1.5 bg-transparent">
              <option value="">{t("pickReplacement")}</option>
              {symbols.filter((s) => s.id !== symbolId).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          )}
          {(op === "add" || op === "reposition") && (
            <select value={placement} onChange={(e) => setPlacement(e.target.value as SymbolPlacement | "")} className="border border-rule px-2 py-1.5 bg-transparent">
              <option value="">{t("placementAuto")}</option>
              {PLACEMENTS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          )}
          <Link href={`/d/${deck.slug}/symbols`} className="text-xs underline">
            {t("needsSymbol")}
          </Link>
        </div>
      )}
      <input value={how} onChange={(e) => setHow(e.target.value.slice(0, 200))} className="border border-rule px-2 py-1.5" placeholder={op === "cosmetic" ? t("cosmeticPrompt") : t("howPlaceholder")} />
      <input value={rationale} onChange={(e) => setRationale(e.target.value.slice(0, 140))} className="border border-ink px-2 py-1.5" placeholder={t("rationale")} required />
      {experiment && (
        <div>
          <div className="text-[10px] uppercase tracking-widest text-muted mb-1">{t("betAxis")}</div>
          <div className="grid grid-cols-2 gap-1 text-xs">
            {AXES.map(([l, r], i) => (
              <button key={i} type="button" onClick={() => setBet(i)} className={`border px-2 py-1 text-left ${bet === i ? "border-accent bg-accent text-paper" : topGaps.includes(i) ? "border-ink" : "border-rule"}`}>
                {l} ↔ {r}
                {gaps && <span className={bet === i ? "text-paper/80" : "text-muted"}> · gap {gaps[i].toFixed(1)}</span>}
              </button>
            ))}
          </div>
        </div>
      )}
      <label className="text-xs flex items-center gap-2">
        {t("candidates")} <input type="number" min={1} max={4} value={n} onChange={(e) => setN(Math.max(1, Math.min(4, Number(e.target.value))))} className="border border-rule w-16 px-1" />
      </label>
      <button type="button" disabled={!complete} onClick={go} className="self-start bg-ink text-paper px-4 py-2">
        {t("generateEdit")}
      </button>
      {err && <p className="text-xs text-accent">{err}</p>}
      {jobId && !job && <JobProgress jobId={jobId} onDone={setJob} />}
      {job?.status === "done" && (
        <Candidates
          job={job}
          kind="edit"
          threshold={deck.settings?.fidelity_threshold ?? 0.85}
          onChoose={(i) => {
            const vid = (job.result as { version_id?: string })?.version_id;
            (vid ? v5.versions.choose(vid, i) : Promise.reject(new Error("no version"))).then(() => (setJob(null), setJobId(null), refresh())).catch((e) => setErr(String(e)));
          }}
        />
      )}
      {job?.status === "failed" && <p className="text-xs text-accent">{job.error}</p>}
      <p className="text-[10px] text-muted">
        {t("currentSymbols")}: {onCard.map((id) => symById.get(id)?.name ?? id).join(", ") || "—"}
      </p>
    </div>
  );
}

function VersionsTab({ card, versions, symById, refresh }: { card: Card; versions: Version[]; symById: Map<string, Symbol>; refresh: () => void }) {
  const t = useTranslations("studio");
  const { atLeast, deck } = useDeckCtx();
  const [a, setA] = useState<string>("");
  const [b, setB] = useState<string>("");
  const [cmp, setCmp] = useState<{ heatmap_url?: string; fidelity?: number; containment?: number } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const branches = [...new Set(versions.map((v) => v.branch_key))];
  return (
    <div className="flex flex-col gap-4 text-sm">
      {branches.map((br) => (
        <div key={br}>
          <div className="text-[10px] uppercase tracking-widest text-muted mb-1">
            {t("branch")} {br}
          </div>
          <ol className="flex gap-2 overflow-x-auto pb-2">
            {versions
              .filter((v) => v.branch_key === br)
              .sort((x, y) => x.v - y.v)
              .map((v) => {
                const e = v.how as { op?: EditOp; bet_axis?: number | null; rationale?: string; editor_name?: string; symbol_id?: string; to_symbol_id?: string };
                return (
                  <li key={v.id} className={`border ${v.id === card.current_version_id ? "border-ink" : "border-rule"} w-28 shrink-0 flex flex-col`}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={imageSrc(v.thumb_url ?? v.image_url) ?? ""} alt="" className="w-full aspect-[11/19] object-cover" />
                    <div className="text-[10px] p-1 flex flex-col gap-0.5">
                      <b>v{v.v}</b>
                      {e.op ? (
                        <span>
                          {e.op} {e.symbol_id ? symById.get(e.symbol_id)?.name ?? e.symbol_id : ""} {e.to_symbol_id ? `→ ${symById.get(e.to_symbol_id)?.name ?? e.to_symbol_id}` : ""}
                        </span>
                      ) : (
                        <span>{(v.how as { mode?: string }).mode ?? "generation"}</span>
                      )}
                      {e.bet_axis != null && <span>bet {AXES[e.bet_axis]?.[0]}↔{AXES[e.bet_axis]?.[1]}</span>}
                      {e.rationale && <span className="text-muted line-clamp-2">“{e.rationale}”</span>}
                      {v.checks?.fidelity != null && <span>F {v.checks.fidelity.toFixed(2)}</span>}
                      <span className="text-muted">n {v.n_readings ?? 0}</span>
                    </div>
                    <div className="flex gap-1 p-1 text-[10px]">
                      <button type="button" className="underline" onClick={() => setA(v.id)}>
                        A
                      </button>
                      <button type="button" className="underline" onClick={() => setB(v.id)}>
                        B
                      </button>
                      {v.id !== card.current_version_id && (
                        <button type="button" className="underline" onClick={() => v5.versions.restore(v.id, window.prompt(t("restoreNote")) ?? "").then(refresh).catch((e2) => setErr(String(e2)))}>
                          {t("restore")}
                        </button>
                      )}
                      {atLeast("curator") && deck.settings?.allow_branches && (
                        <button type="button" className="underline" onClick={() => v5.cards.branch(card.id, { from_version_id: v.id, branch_key: window.prompt(t("branchName")) ?? "" }).then(refresh).catch((e2) => setErr(String(e2)))}>
                          {t("branchBtn")}
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
          </ol>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {t("compare")} A: {a ? `v${versions.find((v) => v.id === a)?.v}` : "—"} · B: {b ? `v${versions.find((v) => v.id === b)?.v}` : "—"}
        <button type="button" disabled={!a || !b} className="border border-ink px-2 py-1" onClick={() => v5.versions.compare(a, b).then(setCmp).catch((e) => setErr(String(e)))}>
          {t("compareBtn")}
        </button>
      </div>
      {cmp && (
        <div className="grid grid-cols-3 gap-2">
          {[a, b].map((id) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={id} src={imageSrc(versions.find((v) => v.id === id)?.image_url) ?? ""} alt="" className="w-full border border-rule" />
          ))}
          <div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {cmp.heatmap_url && <img src={imageSrc(cmp.heatmap_url) ?? ""} alt="" className="w-full border border-rule" />}
            <div className="text-xs mt-1">
              {cmp.fidelity != null && `fidelity ${cmp.fidelity.toFixed(2)} `}
              {cmp.containment != null && `containment ${cmp.containment.toFixed(2)}`}
            </div>
          </div>
        </div>
      )}
      {err && <p className="text-xs text-accent">{err}</p>}
      {versions.length === 0 && <p className="text-muted">{t("noVersionYet")}</p>}
    </div>
  );
}

function ReadingsTab({ cur, ready }: { cur: Version | null; ready: number }) {
  const t = useTranslations("studio");
  const { atLeast } = useDeckCtx();
  const reveal = useLoad(async () => (cur ? v5.versions.reveal(cur.id) : null), [cur?.id]);
  const verdict = useLoad(async () => (cur ? v5.versions.verdict(cur.id).catch(() => null) : null), [cur?.id]);
  if (!cur) return <p className="text-sm text-muted">{t("noVersionYet")}</p>;
  const r = (reveal.data ?? {}) as { readings?: { axes: number[]; free_text?: string | null; d_total?: number; xy?: number[]; prev_xy?: number[]; synthetic?: boolean; nickname?: string }[]; gaps_abs?: { axis: number; abs: number }[]; intent_xy?: number[]; n?: number };
  const readings = r.readings ?? [];
  const n = readings.length || r.n || cur.n_readings || 0;
  return (
    <div className="flex flex-col gap-4 text-sm">
      {reveal.error && reveal.status !== 404 && <ErrorState error={reveal.error} status={reveal.status} />}
      <div>
        {t("collecting")} · {n}/{ready} {verdict.data && `· ${verdict.data.verdict}`}
      </div>
      {r.gaps_abs && (
        <div className="max-w-sm">
          <div className="text-[10px] uppercase tracking-widest text-muted mb-1">{t("gaps")}</div>
          {r.gaps_abs.map((g) => (
            <div key={g.axis} className="flex items-center gap-2 text-xs">
              <span className="w-36 text-right text-muted">
                {AXES[g.axis][0]} ↔ {AXES[g.axis][1]}
              </span>
              <div className="flex-1 h-2 bg-[#e9e3d6]">
                <div className="h-full bg-ink" style={{ width: `${(g.abs / 6) * 100}%` }} />
              </div>
              <span className="w-8 tabular-nums">{g.abs.toFixed(1)}</span>
            </div>
          ))}
        </div>
      )}
      {r.intent_xy && readings.some((x) => x.xy) && (
        <svg viewBox="-8 -8 16 16" className="w-full max-w-sm aspect-square border border-rule bg-[#faf6ee]">
          <circle cx={r.intent_xy[0]} cy={-r.intent_xy[1]} r={0.3 * 6 * Math.sqrt(8)} fill="none" stroke="#d9d2c3" strokeDasharray="0.3 0.2" strokeWidth={0.06} />
          {readings.map((x, i) => (
            <g key={i}>
              {x.prev_xy && x.xy && <line x1={x.prev_xy[0]} y1={-x.prev_xy[1]} x2={x.xy[0]} y2={-x.xy[1]} stroke="#c8361e" strokeWidth={0.08} className="shift-arrow" />}
              {x.xy && <circle cx={x.xy[0]} cy={-x.xy[1]} r={0.25} fill={x.synthetic ? "#9b9b93" : "#c8361e"} />}
            </g>
          ))}
          <text x={r.intent_xy[0]} y={-r.intent_xy[1] + 0.3} fontSize={1} textAnchor="middle">
            ★
          </text>
        </svg>
      )}
      <ul className="text-xs flex flex-col gap-1">
        {readings.map((x, i) => (
          <li key={i} className={`flex gap-2 ${x.synthetic ? "text-muted" : ""}`}>
            <span className="w-24 truncate">{atLeast("curator") ? (x.nickname ?? `#${i + 1}`) : `#${i + 1}`}</span>
            <MiniBars axes={x.axes} width={80} color={x.synthetic ? "#9b9b93" : "#141414"} />
            {x.d_total != null && <span className="tabular-nums">d {x.d_total.toFixed(2)}</span>}
            {x.free_text && <span className="italic">“{x.free_text}”</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function AccessTab({ card, isMaker, refresh }: { card: Card; isMaker: boolean; refresh: () => void }) {
  const t = useTranslations("studio");
  const { deck, members } = useDeckCtx();
  const [mode, setMode] = useState<"policy" | "list">(card.approved_editors === "*" ? "policy" : "list");
  const [list, setList] = useState<string[]>(card.approved_editors === "*" ? [] : card.approved_editors);
  const [msg, setMsg] = useState<string | null>(null);
  const save = (val: "*" | string[]) => v5.cards.update(card.id, { approved_editors: val }).then(() => (setMsg(t("saved")), refresh())).catch((e) => setMsg(String(e)));
  return (
    <div className="flex flex-col gap-4 text-sm max-w-lg">
      <p className="text-xs text-muted">{t("accessRule")}</p>
      <div className="flex gap-2">
        <button type="button" disabled={!isMaker} onClick={() => (setMode("policy"), save("*"))} className={`border px-3 py-1 ${mode === "policy" ? "border-ink bg-ink text-paper" : "border-rule"}`}>
          {t("policyInherited", { policy: deck.settings?.default_editor_policy ?? "any_member" })}
        </button>
        <button type="button" disabled={!isMaker} onClick={() => setMode("list")} className={`border px-3 py-1 ${mode === "list" ? "border-ink bg-ink text-paper" : "border-rule"}`}>
          {t("makersList")}
        </button>
      </div>
      {mode === "list" && (
        <div className="flex flex-col gap-1 text-xs">
          {(members ?? []).map((m) => (
            <label key={m.user_id} className="flex items-center gap-2">
              <input type="checkbox" disabled={!isMaker} checked={list.includes(m.user_id)} onChange={(e) => setList(e.target.checked ? [...list, m.user_id] : list.filter((x) => x !== m.user_id))} />
              {m.user?.name ?? m.user_id} · {m.role}
            </label>
          ))}
          {!members && <span className="text-muted">{t("membersUnavailable")}</span>}
          {isMaker && (
            <button type="button" className="self-start bg-ink text-paper px-3 py-1.5 mt-1" onClick={() => save(list)}>
              {t("save")}
            </button>
          )}
        </div>
      )}
      <div>
        <div className="text-[10px] uppercase tracking-widest text-muted mb-1">{t("editRequests")}</div>
        <ul className="flex flex-col gap-1 text-xs">
          {(card.edit_requests ?? []).map((r, i) => (
            <li key={r.id ?? i} className="flex items-center gap-2 border border-rule px-2 py-1">
              <span className="flex-1">
                <b>{r.user_name ?? r.user_id}</b> · “{r.note}” · {r.status}
              </span>
              {isMaker && r.status === "open" && r.id && (
                <>
                  <button type="button" className="bg-ink text-paper px-2 py-0.5" onClick={() => v5.cards.decideRequest(card.id, r.id!, "approved").then(refresh)}>
                    {t("approvePerson")}
                  </button>
                  <button type="button" className="border border-rule px-2 py-0.5" onClick={() => v5.cards.decideRequest(card.id, r.id!, "declined").then(refresh)}>
                    {t("decline")}
                  </button>
                </>
              )}
            </li>
          ))}
          {(card.edit_requests ?? []).length === 0 && <li className="text-muted">—</li>}
        </ul>
      </div>
      {msg && <p className="text-xs text-muted">{msg}</p>}
    </div>
  );
}

export default function CardStudioPage() {
  return (
    <Suspense fallback={null}>
      <Studio />
    </Suspense>
  );
}

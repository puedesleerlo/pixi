"use client";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import Dots from "@/components/Dots";
import { useDeckCtx } from "@/components/ws/DeckContext";
import { imageSrc, v5 } from "@/lib/api";
import type { Axes8, Version } from "@/lib/types";

/** The deck's reading queue (spec §5.8): the version with the fewest human readings. */
export default function ReadQueuePage() {
  const t = useTranslations("read");
  const { deck } = useDeckCtx();
  const [task, setTask] = useState<{ card_id: string; version: Version; previous_axes: Axes8 | null } | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "empty" | "done" | "error">("loading");
  const [reason, setReason] = useState<string | null>(null);
  const [axes, setAxes] = useState<(number | null)[]>(Array(8).fill(null));
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [started, setStarted] = useState(0);
  const load = () => {
    setState("loading");
    setAxes(Array(8).fill(null));
    setText("");
    v5.decks
      .readNext(deck.id)
      .then((r) => {
        if (r.empty || !r.version || !r.card_id) {
          setReason((r as unknown as { reason?: string }).reason ?? null);
          setState("empty");
        }
        else {
          setTask({ card_id: r.card_id, version: r.version, previous_axes: r.previous_axes ?? null, intent_missing: !!(r as unknown as { intent_missing?: boolean }).intent_missing } as typeof task extends infer T ? (T extends null ? never : T) & { intent_missing?: boolean } : never);
          setStarted(Date.now());
          setState("ready");
        }
      })
      .catch((e) => {
        setErr(e instanceof Error ? e.message : String(e));
        setState("error");
      });
  };
  useEffect(load, [deck.id]);
  const complete = axes.every((v) => v !== null);
  return (
    <div className="max-w-md flex flex-col gap-4">
      <h1 className="font-display text-2xl">{t("title")}</h1>
      {state === "empty" && (
        <p className="text-sm text-muted">
          {reason === "all_read" ? t("emptyAllRead") : reason === "own_cards_only" ? t("emptyOwnOnly") : reason === "no_cards" ? t("emptyNoCards") : t("empty")}
        </p>
      )}
      {state === "error" && <p className="text-sm text-accent">{err}</p>}
      {state === "done" && (
        <div className="text-sm flex flex-col gap-2">
          <p>{t("thanks")}</p>
          <button type="button" className="self-start border border-ink px-3 py-1.5" onClick={load}>
            {t("another")}
          </button>
        </div>
      )}
      {state === "ready" && task && (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={imageSrc(task.version.image_url) ?? ""} alt="" className="w-full border border-ink" />
          <p className="text-xs text-muted">{t("instructions")}</p>
          {(task as unknown as { intent_missing?: boolean }).intent_missing && <p className="text-xs text-accent">{t("noIntentYet")}</p>}
          <Dots values={axes} onChange={(i, v) => setAxes((a) => a.map((x, j) => (j === i ? v : x)))} ghosts={task.previous_axes ?? undefined} />
          <input value={text} onChange={(e) => setText(e.target.value.slice(0, 140))} placeholder={t("phrase")} className="border border-rule px-3 py-2 text-sm" />
          <button
            type="button"
            disabled={!complete}
            className="bg-ink text-paper py-3"
            onClick={() =>
              v5.versions
                .submitReading(task.version.id, { axes: axes.map((v) => v ?? 0), free_text: text || undefined, latency_ms: Date.now() - started })
                .then(() => setState("done"))
                .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
            }
          >
            {complete ? t("submit") : t("submitN", { n: axes.filter((v) => v !== null).length })}
          </button>
        </>
      )}
    </div>
  );
}

"use client";
import { useState } from "react";
import { useTranslations } from "next-intl";
import JobProgress from "@/components/JobProgress";
import { useDeckCtx } from "@/components/ws/DeckContext";
import { v5 } from "@/lib/api";

export default function ReinterpretPage() {
  const t = useTranslations("cards");
  const { deck } = useDeckCtx();
  const [group, setGroup] = useState("all");
  const [job, setJob] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const positions = deck.structure?.positions ?? [];
  const groups = [...new Set(positions.map((p) => p.group))];
  return (
    <div className="flex flex-col gap-4 max-w-lg text-sm">
      <h1 className="font-display text-2xl">{t("reinterpret")}</h1>
      <p className="text-muted">{t("reinterpretHint")}</p>
      <select value={group} onChange={(e) => setGroup(e.target.value)} className="border border-rule px-2 py-1.5 bg-transparent">
        <option value="all">{t("allPositions")}</option>
        {groups.map((g) => (
          <option key={g} value={g}>
            {g}
          </option>
        ))}
      </select>
      <button
        type="button"
        className="bg-ink text-paper px-4 py-2 self-start"
        onClick={() =>
          v5.decks
            .reinterpret(deck.id, { base_deck_id: deck.origin?.base_deck_id ?? "", positions: group === "all" ? undefined : positions.filter((p) => p.group === group).map((p) => p.key) })
            .then((j) => setJob(j.id))
            .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
        }
      >
        {t("startBatch")}
      </button>
      {job && <JobProgress jobId={job} />}
      {err && <p className="text-accent">{err}</p>}
    </div>
  );
}

"use client";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { subscribeJob } from "@/lib/sse";
import type { Job } from "@/lib/types";

/** Progress bar bound to a job over SSE (polling fallback). Calls onDone with the finished job. */
export default function JobProgress({ jobId, onDone }: { jobId: string; onDone?: (job: Job) => void }) {
  const t = useTranslations("jobs");
  const [job, setJob] = useState<Job | null>(null);
  useEffect(() => {
    if (!jobId) return;
    return subscribeJob(jobId, (j) => {
      setJob(j);
      if (j.status === "done" || j.status === "failed") onDone?.(j);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);
  const pct = Math.round((job?.progress ?? 0) * 100);
  return (
    <div className="border border-rule px-3 py-2 text-xs">
      <div className="flex justify-between">
        <span>
          {t("job")} {job?.kind ?? ""} · {job?.status ?? t("queued")}
        </span>
        <span className="tabular-nums">{pct}%</span>
      </div>
      <div className="h-1.5 bg-[#e9e3d6] mt-1">
        <div className="h-full bg-ink transition-all duration-500" style={{ width: `${pct}%` }} />
      </div>
      {job?.note && <div className="text-muted mt-1">{job.note}</div>}
      {job?.status === "failed" && <div className="text-accent mt-1">{job.error ?? t("failed")}</div>}
    </div>
  );
}

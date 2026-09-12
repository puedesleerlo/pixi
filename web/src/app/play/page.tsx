"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { getNickname, setNickname, v5 } from "@/lib/api";

function PlayInner() {
  const t = useTranslations("play");
  const router = useRouter();
  const sp = useSearchParams();
  const [code, setCode] = useState(sp.get("code")?.toUpperCase() ?? "");
  const [nick, setNick] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setNick(getNickname()), []);
  async function join(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      setNickname(nick);
      const s = await v5.sessions.join(code, nick);
      router.push(`/s/${s.code}`);
    } catch (er) {
      // v4 rooms keep working while sessions (slice 8) land: fall back to the relay room route.
      const msg = er instanceof Error ? er.message : String(er);
      if (/404|no such/i.test(msg)) router.push(`/r/${code}`);
      else setErr(msg);
      setBusy(false);
    }
  }
  return (
    <form onSubmit={join} className="max-w-md mx-auto px-4 py-10 flex flex-col gap-4">
      <h1 className="font-display text-3xl">{t("title")}</h1>
      <p className="text-sm text-muted">{t("sub")}</p>
      <label className="text-xs uppercase tracking-widest text-muted">{t("nickname")}</label>
      <input value={nick} onChange={(e) => setNick(e.target.value.slice(0, 24))} className="border border-ink px-3 py-3" placeholder="e.g. ana" />
      <label className="text-xs uppercase tracking-widest text-muted">{t("code")}</label>
      <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 4))} className="border border-ink px-3 py-3 font-display text-3xl tracking-[0.3em]" placeholder="CODE" />
      <button type="submit" disabled={busy || code.length !== 4 || !nick.trim()} className="bg-ink text-paper py-3">
        {t("join")}
      </button>
      {err && <p className="text-sm text-accent">{err}</p>}
    </form>
  );
}

export default function PlayPage() {
  return (
    <Suspense fallback={null}>
      <PlayInner />
    </Suspense>
  );
}

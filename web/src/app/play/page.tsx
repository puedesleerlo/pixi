"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { ApiError, getNickname, setNickname, setToken, v5 } from "@/lib/api";
import { scanSessionCode } from "@/lib/scan";

function PlayInner() {
  const t = useTranslations("play");
  const router = useRouter();
  const sp = useSearchParams();
  const [code, setCode] = useState(sp.get("code")?.toUpperCase() ?? "");
  const [nick, setNick] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [scanHint, setScanHint] = useState<string | null>(null);
  useEffect(() => setNick(getNickname()), []);

  async function join(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      setNickname(nick);
      let s;
      try {
        s = await v5.sessions.join(code, nick);
      } catch (er) {
        if (er instanceof ApiError && er.status === 401) {
          const g = await v5.auth.guest(nick);
          if (g.token) setToken(g.token);
          s = await v5.sessions.join(code, nick);
        } else throw er;
      }
      try {
        sessionStorage.setItem(`pixie_sid_${s.code}`, s.id);
      } catch {}
      router.push(`/s/${s.code}`);
    } catch (er) {
      const msg = er instanceof Error ? er.message : String(er);
      if (er instanceof ApiError && er.status === 404) setErr(t("noSuchSession"));
      else if (er instanceof ApiError && er.status === 403) setErr(t("guestsNotAllowed"));
      else setErr(msg);
      setBusy(false);
    }
  }

  async function scan() {
    setScanHint(null);
    try {
      const found = await scanSessionCode();
      if (!found) setScanHint(t("scanTimeout"));
      else if (/^[A-Z]{4}$/.test(found)) setCode(found);
      else router.push(found);
    } catch {
      setScanHint(t("scanUnsupported"));
    }
  }

  return (
    <form onSubmit={join} className="max-w-md mx-auto px-4 py-10 flex flex-col gap-4">
      <h1 className="font-display text-3xl">{t("title")}</h1>
      <p className="text-sm text-muted">{t("sub")}</p>
      <label className="text-xs uppercase tracking-widest text-muted">{t("nickname")}</label>
      <input value={nick} onChange={(e) => setNick(e.target.value.slice(0, 24))} className="border border-ink px-3 py-3" placeholder="e.g. ana" />
      <label className="text-xs uppercase tracking-widest text-muted">{t("code")}</label>
      <div className="flex gap-2">
        <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 4))} className="flex-1 border border-ink px-3 py-3 font-display text-3xl tracking-[0.3em]" placeholder="CODE" />
        <button type="button" onClick={scan} className="border border-ink px-3 text-sm">
          {t("scan")}
        </button>
      </div>
      {scanHint && <p className="text-xs text-muted">{scanHint}</p>}
      <button type="submit" disabled={busy || code.length !== 4 || !nick.trim()} className="bg-ink text-paper py-3">
        {busy ? t("joining") : t("join")}
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

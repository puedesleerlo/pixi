"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { apiUrl, setToken, v5 } from "@/lib/api";

export default function SignInPage() {
  const t = useTranslations("auth");
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [loginUrl, setLoginUrl] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function magic(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const r = await v5.auth.magic(email.trim());
      if (r.login_url) setLoginUrl(r.login_url);
      else setSent(true);
    } catch (er) {
      setErr(er instanceof Error ? er.message : String(er));
    } finally {
      setBusy(false);
    }
  }
  async function guest() {
    setBusy(true);
    try {
      const r = await v5.auth.guest();
      if (r.token) setToken(r.token);
      router.push("/");
      router.refresh();
    } catch (er) {
      setErr(er instanceof Error ? er.message : String(er));
      setBusy(false);
    }
  }
  return (
    <div className="max-w-md mx-auto px-4 py-10 flex flex-col gap-6">
      <h1 className="font-display text-3xl">{t("title")}</h1>
      <form onSubmit={magic} className="flex flex-col gap-2">
        <label className="text-xs uppercase tracking-widest text-muted">{t("email")}</label>
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="border border-ink px-3 py-2" placeholder="you@example.org" />
        <button type="submit" disabled={busy || !email} className="bg-ink text-paper py-2.5">
          {t("sendLink")}
        </button>
      </form>
      {loginUrl && (
        <div className="border border-accent px-3 py-3 text-sm">
          <div className="text-xs uppercase tracking-widest text-accent">{t("devBanner")}</div>
          <p className="mt-1 text-muted">{t("noMailProvider")}</p>
          <a href={loginUrl} className="underline break-all">
            {loginUrl}
          </a>
        </div>
      )}
      {sent && <p className="text-sm">{t("checkInbox")}</p>}
      <a href={`${apiUrl()}/api/auth/auth0/login`} className="border border-ink py-2.5 text-center">
        {t("google")}
      </a>
      <button type="button" onClick={guest} disabled={busy} className="border border-rule py-2.5 text-muted">
        {t("continueGuest")}
      </button>
      {err && <p className="text-sm text-accent">{err}</p>}
      <p className="text-xs text-muted">{t("guestNote")}</p>
    </div>
  );
}

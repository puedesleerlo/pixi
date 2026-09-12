"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { setToken, v5 } from "@/lib/api";

export default function MagicPage() {
  const t = useTranslations("auth");
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    v5.auth
      .magicVerify(token)
      .then((r) => {
        if (r.token) setToken(r.token);
        router.replace("/");
        router.refresh();
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [token, router]);
  return (
    <div className="max-w-md mx-auto px-4 py-16 text-center">
      <p className="font-display text-xl">{err ? t("linkInvalid") : t("signingIn")}</p>
      {err && <p className="text-sm text-accent mt-2">{err}</p>}
    </div>
  );
}

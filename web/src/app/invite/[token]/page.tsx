"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { v5 } from "@/lib/api";

export default function InvitePage() {
  const t = useTranslations("members");
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    v5.members
      .accept(token)
      .then((m) => router.replace(`/d/${m.deck_id}`))
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [token, router]);
  return <div className="max-w-md mx-auto px-4 py-16 text-center text-sm">{err ? <span className="text-accent">{err}</span> : t("accepting")}</div>;
}

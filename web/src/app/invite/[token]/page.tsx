"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { v5 } from "@/lib/api";
import { useMe } from "@/lib/hooks";

/** Accept an invitation link. Waits for the visitor's identity (a temporary guest is created on first
 *  contact) before accepting, so the request always carries a session. */
export default function InvitePage() {
  const t = useTranslations("members");
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const { data: me, loading } = useMe();
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (loading || !me) return;
    v5.members
      .accept(token)
      .then((m) => router.replace(`/d/${m.deck_id}`))
      .catch((e) => {
        const status = (e as { status?: number })?.status;
        setErr(status === 404 ? t("inviteGone") : e instanceof Error ? e.message : String(e));
      });
  }, [token, router, me, loading]);
  return (
    <div className="max-w-md mx-auto px-4 py-16 text-center text-sm">
      {err ? <span className="text-accent">{err}</span> : t("accepting")}
    </div>
  );
}

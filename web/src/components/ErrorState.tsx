"use client";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ApiError } from "@/lib/api";

/** One place for 401 / 403 / 404 / network failures, with a sign-in link where it helps. */
export default function ErrorState({ error, status }: { error: Error | null; status?: number | null }) {
  const t = useTranslations("errors");
  const code = status ?? (error instanceof ApiError ? error.status : null);
  const title = code === 401 ? t("401") : code === 403 ? t("403") : code === 404 ? t("404") : code === 0 || !code ? t("network") : t("generic", { code });
  return (
    <div className="border border-rule px-4 py-6 my-6 max-w-lg">
      <div className="font-display text-xl">{title}</div>
      {error?.message && <p className="text-sm text-muted mt-1">{error.message}</p>}
      {(code === 401 || code === 403) && (
        <Link href="/auth/sign-in" className="inline-block mt-3 border border-ink px-3 py-1.5 text-sm">
          {t("signIn")}
        </Link>
      )}
    </div>
  );
}

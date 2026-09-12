"use client";
import Link from "next/link";
import { useTranslations } from "next-intl";
import ErrorState from "@/components/ErrorState";
import { v5 } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export default function NotificationsPage() {
  const t = useTranslations("me");
  const l = useLoad(() => v5.notifications.list(), []);
  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <h1 className="font-display text-3xl mb-4">{t("notifications")}</h1>
      {l.error && <ErrorState error={l.error} status={l.status} />}
      <ul className="flex flex-col gap-2 text-sm">
        {l.data?.map((n) => (
          <li key={n.id} className={`border px-3 py-2 ${n.read_at ? "border-rule text-muted" : "border-ink"}`}>
            <div className="flex justify-between gap-2">
              <span>{n.text}</span>
              {!n.read_at && (
                <button type="button" className="text-xs underline" onClick={() => v5.notifications.markRead(n.id).then(l.refresh)}>
                  {t("markRead")}
                </button>
              )}
            </div>
            {n.card_id && n.deck_id && (
              <Link href={`/d/${n.deck_id}/cards/${n.card_id}`} className="text-xs underline">
                {t("openCard")}
              </Link>
            )}
          </li>
        ))}
        {l.data && l.data.length === 0 && <li className="text-muted">—</li>}
      </ul>
    </div>
  );
}

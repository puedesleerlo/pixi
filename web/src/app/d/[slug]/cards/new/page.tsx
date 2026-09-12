"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useDeckCtx } from "@/components/ws/DeckContext";
import { v5 } from "@/lib/api";

/** Creates the Card record for a position (or a free card), then opens the studio on the Generate tab. */
function NewCardInner() {
  const t = useTranslations("cards");
  const { deck } = useDeckCtx();
  const sp = useSearchParams();
  const router = useRouter();
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    v5.cards
      .create(deck.id, { position_key: sp.get("position") ?? undefined })
      .then((c) => router.replace(`/d/${deck.slug}/cards/${c.id}?tab=generate`))
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [deck.id, deck.slug, sp, router]);
  return <p className="text-sm text-muted">{err ? `${t("createFailed")}: ${err}` : t("creating")}</p>;
}
export default function NewCardPage() {
  return (
    <Suspense fallback={null}>
      <NewCardInner />
    </Suspense>
  );
}

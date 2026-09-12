"use client";
import { useTranslations } from "next-intl";
import DeckTile from "@/components/DeckTile";
import ErrorState from "@/components/ErrorState";
import { v5 } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

export default function MyDecksPage() {
  const t = useTranslations("me");
  const l = useLoad(() => v5.auth.myDecks(), []);
  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <h1 className="font-display text-3xl mb-4">{t("decks")}</h1>
      {l.error && <ErrorState error={l.error} status={l.status} />}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{l.data?.map((d) => <DeckTile key={d.id} deck={d} chips={[d.my_role ?? ""]} />)}</div>
    </div>
  );
}

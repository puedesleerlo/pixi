"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import ErrorState from "@/components/ErrorState";
import LocaleToggle from "@/components/LocaleToggle";
import { setToken, v5 } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import type { Deck } from "@/lib/types";

export default function MePage() {
  const t = useTranslations("me");
  const router = useRouter();
  const { data: me, loading, isGuest } = useMe();
  const [decks, setDecks] = useState<Deck[]>([]);
  const [email, setEmail] = useState("");
  const [upgradeUrl, setUpgradeUrl] = useState<string | null>(null);
  const [name, setName] = useState("");
  useEffect(() => {
    if (me) {
      setName(me.name);
      v5.auth.myDecks().then(setDecks).catch(() => {});
    }
  }, [me]);
  if (!loading && !me) return <div className="max-w-2xl mx-auto px-4"><ErrorState error={null} status={401} /></div>;
  return (
    <div className="max-w-2xl mx-auto px-4 py-8 flex flex-col gap-8">
      <header>
        <div className="text-xs uppercase tracking-widest text-muted">{t("profile")}</div>
        <h1 className="font-display text-3xl">{me?.name}</h1>
        <div className="text-sm text-muted">{isGuest ? t("guest") : me?.email}</div>
      </header>
      <section className="flex flex-col gap-2">
        <label className="text-xs uppercase tracking-widest text-muted">{t("displayName")}</label>
        <div className="flex gap-2">
          <input value={name} onChange={(e) => setName(e.target.value.slice(0, 40))} className="border border-ink px-3 py-2 flex-1" />
          <button type="button" className="border border-ink px-3" onClick={() => v5.auth.updateMe({ name }).then(() => router.refresh())}>
            {t("save")}
          </button>
        </div>
        <div className="flex items-center gap-3 mt-2 text-sm">
          <span>{t("language")}</span>
          <LocaleToggle />
        </div>
      </section>
      {isGuest && (
        <section className="border border-rule p-4 flex flex-col gap-2">
          <div className="font-display text-lg">{t("upgradeTitle")}</div>
          <p className="text-sm text-muted">{t("upgradeSub")}</p>
          <div className="flex gap-2">
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="border border-ink px-3 py-2 flex-1" placeholder="you@example.org" />
            <button
              type="button"
              className="bg-ink text-paper px-3"
              onClick={() =>
                v5.auth.upgrade(email).then((r) => {
                  if (r.login_url) setUpgradeUrl(r.login_url);
                  else router.refresh();
                })
              }
            >
              {t("upgrade")}
            </button>
          </div>
          {upgradeUrl && (
            <a href={upgradeUrl} className="text-xs underline break-all">
              {upgradeUrl}
            </a>
          )}
        </section>
      )}
      <section>
        <h2 className="font-display text-xl mb-2">{t("decks")}</h2>
        <ul className="text-sm flex flex-col gap-1">
          {decks.map((d) => (
            <li key={d.id}>
              <Link href={`/d/${d.slug}`} className="underline underline-offset-2">
                {d.name}
              </Link>{" "}
              <span className="text-muted">· {d.my_role ?? ""}</span>
            </li>
          ))}
          {decks.length === 0 && <li className="text-muted">—</li>}
        </ul>
      </section>
      <section className="text-sm text-muted">
        <h2 className="font-display text-xl mb-2 text-ink">{t("contributions")}</h2>
        <p>{t("contributionsPrivate")}</p>
      </section>
      <button
        type="button"
        className="self-start border border-rule px-3 py-2 text-sm"
        onClick={() =>
          v5.auth.logout().finally(() => {
            setToken(null);
            router.push("/");
            router.refresh();
          })
        }
      >
        {t("signOut")}
      </button>
    </div>
  );
}

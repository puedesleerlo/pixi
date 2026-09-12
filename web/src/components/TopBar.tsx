"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import LocaleToggle from "@/components/LocaleToggle";
import { v5 } from "@/lib/api";
import { useMe } from "@/lib/hooks";

/** Global navigation (spec §4.1). Guests: Home · Explore · Play · Sign in. */
export default function TopBar() {
  const t = useTranslations("nav");
  const path = usePathname();
  const { data: me, signedIn } = useMe();
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    if (!signedIn) return;
    v5.notifications
      .list()
      .then((n) => setUnread(n.filter((x) => !x.read_at).length))
      .catch(() => {});
  }, [signedIn]);
  const active = (h: string) => (h === "/" ? path === "/" : path.startsWith(h));
  const link = (href: string, label: string) => (
    <Link key={href} href={href} className={active(href) ? "underline underline-offset-4 decoration-accent" : "text-muted hover:text-ink"}>
      {label}
    </Link>
  );
  return (
    <nav className="w-full border-b border-rule bg-paper sticky top-0 z-30">
      <div className="max-w-6xl mx-auto px-4 h-11 flex items-center justify-between gap-4">
        <Link href="/" className="font-display text-lg tracking-wide">
          PIXIE
        </Link>
        <div className="flex items-center gap-3 sm:gap-4 text-sm whitespace-nowrap min-w-0">
          <span className="hidden sm:contents">{link("/", t("home"))}</span>
          {link("/explore", t("explore"))}
          {signedIn && <span className="hidden sm:contents">{link("/me/decks", t("myDecks"))}</span>}
          {link("/play", t("play"))}
          {signedIn && (
            <Link href="/me/notifications" className={`relative hidden sm:inline ${active("/me/notifications") ? "underline underline-offset-4 decoration-accent" : "text-muted hover:text-ink"}`}>
              {t("notifications")}
              {unread > 0 && <span className="ml-1 text-[10px] bg-accent text-paper px-1 rounded-full">{unread}</span>}
            </Link>
          )}
          {signedIn ? (
            <Link href="/me" className={active("/me") && !path.startsWith("/me/") ? "underline underline-offset-4 decoration-accent" : "text-muted hover:text-ink"}>
              {me?.name || t("profile")}
            </Link>
          ) : (
            <Link href="/auth/sign-in" className="border border-ink px-2 py-0.5 shrink-0 bg-ink text-paper">
              {t("signIn")}
            </Link>
          )}
          <LocaleToggle className="hidden sm:flex" />
        </div>
      </div>
    </nav>
  );
}

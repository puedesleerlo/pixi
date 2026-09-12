"use client";
import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { setLocaleCookie, type Locale } from "@/lib/locale";
import { v5 } from "@/lib/api";

export default function LocaleToggle({ className = "" }: { className?: string }) {
  const locale = useLocale() as Locale;
  const router = useRouter();
  const set = (l: Locale) => {
    setLocaleCookie(l);
    v5.auth.updateMe({ locale: l }).catch(() => {});
    router.refresh();
  };
  return (
    <div className={`flex items-center gap-1 text-xs ${className}`} aria-label="language">
      {(["en", "es"] as Locale[]).map((l) => (
        <button key={l} type="button" onClick={() => set(l)} className={`px-1.5 py-0.5 border ${locale === l ? "border-ink bg-ink text-paper" : "border-rule text-muted"}`}>
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

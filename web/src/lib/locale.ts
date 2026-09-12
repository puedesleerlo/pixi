"use client";
/** Locale lives in the NEXT_LOCALE cookie (guests) and on User.locale (accounts). */
export type Locale = "en" | "es";

export function setLocaleCookie(locale: Locale) {
  try {
    document.cookie = `NEXT_LOCALE=${locale}; path=/; max-age=31536000; samesite=lax`;
  } catch {}
}

export function readLocaleCookie(): Locale {
  try {
    const m = document.cookie.match(/(?:^|; )NEXT_LOCALE=(en|es)/);
    return (m?.[1] as Locale) ?? "en";
  } catch {
    return "en";
  }
}

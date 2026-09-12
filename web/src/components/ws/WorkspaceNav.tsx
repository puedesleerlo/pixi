"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useDeckCtx } from "@/components/ws/DeckContext";
import type { EffectiveRole } from "@/lib/types";

/** Left navigation of the deck workspace (spec §4.4); items shown per role; bottom sheet on phones. */
export default function WorkspaceNav() {
  const t = useTranslations("ws");
  const { deck, role, atLeast } = useDeckCtx();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const base = `/d/${deck.slug}`;
  const items: { href: string; label: string; min: EffectiveRole }[] = [
    { href: base, label: t("overview"), min: "guest" },
    { href: `${base}/cards`, label: t("cards"), min: "guest" },
    { href: `${base}/symbols`, label: t("symbols"), min: "guest" },
    { href: `${base}/play`, label: t("play"), min: "guest" },
    { href: `${base}/grammar`, label: t("grammar"), min: "guest" },
    { href: `${base}/history`, label: t("history"), min: "guest" },
    { href: `${base}/members`, label: t("members"), min: "guest" },
    { href: `${base}/settings`, label: t("settings"), min: "curator" },
  ];
  const visible = items.filter((i) => atLeast(i.min));
  const active = (h: string) => (h === base ? path === base : path.startsWith(h));
  const list = (
    <ul className="flex flex-col gap-1 text-sm">
      {visible.map((i) => (
        <li key={i.href}>
          <Link href={i.href} onClick={() => setOpen(false)} className={`block px-2 py-1.5 ${active(i.href) ? "bg-ink text-paper" : "hover:bg-[#ece6d8]"}`}>
            {i.label}
          </Link>
        </li>
      ))}
    </ul>
  );
  return (
    <>
      <aside className="hidden md:block w-44 shrink-0 pr-4 border-r border-rule">
        <div className="text-[10px] uppercase tracking-widest text-muted mb-2">
          {t("yourRole")}: {role}
        </div>
        {list}
      </aside>
      <div className="md:hidden fixed bottom-0 left-0 right-0 z-30">
        {open && (
          <div className="bg-paper border-t border-rule px-4 py-3 max-h-[60vh] overflow-auto">
            <div className="text-[10px] uppercase tracking-widest text-muted mb-2">
              {t("yourRole")}: {role}
            </div>
            {list}
          </div>
        )}
        <button type="button" onClick={() => setOpen((o) => !o)} className="w-full bg-ink text-paper py-2 text-sm">
          {open ? t("closeMenu") : `${t("menu")} · ${visible.find((i) => active(i.href))?.label ?? ""}`}
        </button>
      </div>
    </>
  );
}

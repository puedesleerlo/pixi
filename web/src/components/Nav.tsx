"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Play", match: (p: string) => p === "/" || p.startsWith("/r/") },
  { href: "/decks/PLAY", label: "Deck", match: (p: string) => p.startsWith("/decks") && !p.endsWith("/grammar") },
  { href: "/grammar", label: "Grammar", match: (p: string) => p.startsWith("/grammar") || p.endsWith("/grammar") },
];

export default function Nav() {
  const path = usePathname();
  return (
    <nav className="w-full border-b border-rule">
      <div className="max-w-3xl mx-auto px-4 h-11 flex items-center justify-between">
        <Link href="/" className="font-display text-lg tracking-wide">
          PIXIE
        </Link>
        <div className="flex gap-5 text-sm">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className={l.match(path) ? "underline underline-offset-4 decoration-accent" : "text-muted hover:text-ink"}>
              {l.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}

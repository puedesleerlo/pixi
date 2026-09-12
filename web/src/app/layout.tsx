import type { Metadata, Viewport } from "next";
import { Fraunces } from "next/font/google";
import "./globals.css";
import Nav from "@/components/Nav";

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  display: "swap",
  axes: ["opsz"],
});

export const metadata: Metadata = {
  title: "PIXIE",
  description:
    "A multiplayer relay on public-domain tarot symbols. Every edit is an experiment; the experiments add up to a symbol grammar.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={fraunces.variable}>
      <body className="min-h-dvh flex flex-col bg-paper text-ink antialiased">
        <Nav />
        <main className="flex-1 w-full max-w-3xl mx-auto px-4 pb-16">{children}</main>
        <footer className="w-full border-t border-rule px-4 py-4 text-[11px] leading-snug text-muted max-w-3xl mx-auto">
          A visual-communication research tool. No prediction claims. Symbols cut from Smith 1909 and Conver 1760,
          public domain.
        </footer>
      </body>
    </html>
  );
}

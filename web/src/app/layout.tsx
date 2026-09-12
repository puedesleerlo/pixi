import type { Metadata, Viewport } from "next";
import { Fraunces } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import "./globals.css";
import TopBar from "@/components/TopBar";

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  display: "swap",
  axes: ["opsz"],
});

export const metadata: Metadata = {
  title: "PIXIE",
  description: "Communities build decks together. Every deck has its own symbols, its own style, and its own evidence of what its cards actually communicate.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, maximumScale: 1 };

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const locale = await getLocale();
  const messages = await getMessages();
  return (
    <html suppressHydrationWarning lang={locale} className={fraunces.variable}>
      <body className="min-h-dvh flex flex-col bg-paper text-ink antialiased">
        <NextIntlClientProvider messages={messages}>
          <TopBar />
          <main className="flex-1 w-full">{children}</main>
          <footer className="w-full border-t border-rule px-4 py-4 text-[11px] leading-snug text-muted">
            <div className="max-w-6xl mx-auto">
              {locale === "es"
                ? "Una herramienta de investigación en comunicación visual. Sin afirmaciones predictivas. Barajas históricas de dominio público."
                : "A visual-communication research tool. No prediction claims. Historical decks in the public domain."}
            </div>
          </footer>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}

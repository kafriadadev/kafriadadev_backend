import type { Metadata, Viewport } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { body, display, mono } from "./fonts";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return {
    title: { default: t("title"), template: t("titleTemplate") },
    description: t("description"),
    robots: { index: true, follow: true },
    icons: { icon: "/brand/kafriada-net-mark.svg" },
  };
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // maximumScale is deliberately not set: people read a 24-character ID off a
  // small screen, and blocking zoom fails WCAG.
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  const t = await getTranslations("nav");
  return (
    <html lang={locale === "en" ? "en-NG" : locale} className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <body>
        <a href="#main" className="sr-only z-50 rounded-pill bg-boot px-4 py-3 font-bold text-chalk focus:not-sr-only focus:fixed focus:left-4 focus:top-4">{t("skip")}</a>
        <SiteHeader />
        <main id="main">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}

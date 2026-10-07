import type { Metadata, Viewport } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import Script from "next/script";
import { Suspense } from "react";
import { NavProgress } from "@/components/ui/NavProgress";
import { ServiceWorker } from "@/components/ui/ServiceWorker";
import { fontVariables } from "./fonts";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return {
    title: { default: t("title"), template: t("titleTemplate") },
    description: t("description"),
    robots: { index: true, follow: true },
    icons: { icon: "/brand/kafriada-net-mark.svg", apple: "/icons/apple-touch-icon.png" },
  };
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // The logo's green for the phone's address bar; tokens.css is the source.
  themeColor: "#0EAD2C",
  // maximumScale is deliberately not set: people read a 24-character ID off a
  // small screen, and blocking zoom fails WCAG.
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale();
  const t = await getTranslations("nav");
  const tu = await getTranslations("ui");
  return (
    <html lang={locale === "en" ? "en-NG" : locale} className={fontVariables}>
      <body>
        <a href="#main" className="sr-only z-50 rounded-pill bg-boot px-4 py-3 font-bold text-chalk focus:not-sr-only focus:fixed focus:left-4 focus:top-4">{t("skip")}</a>
        <SiteHeader />
        <main id="main">{children}</main>
        <SiteFooter />
        <ServiceWorker />
        <Suspense fallback={null}>
          <NavProgress label={tu("loading")} />
        </Suspense>
        {/* Layer 2: hairline figures on capable devices, when the browser is idle. */}
        <Script src="/delight.js" strategy="lazyOnload" />
      </body>
    </html>
  );
}

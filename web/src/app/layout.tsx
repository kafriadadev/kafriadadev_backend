import type { Metadata, Viewport } from "next";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

export const metadata: Metadata = {
  title: {
    default: "KAFRIADA NET — your permanent football ID",
    template: "%s · KAFRIADA NET",
  },
  description:
    "Register free and receive a permanent KAFRIADA NET ID with a QR profile any club or scout can check. Jigawa State pilot.",
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // maximumScale is deliberately not set. Preventing zoom on a page where
  // people read a 24-character identifier off a small screen would be a
  // cruelty, and it fails WCAG.
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-NG">
      <body>
        <a href="#main">Skip to content</a>
        <SiteHeader />
        <main id="main">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}

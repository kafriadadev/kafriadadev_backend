import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "KAFRIADA — your permanent sports ID",
    template: "%s · KAFRIADA",
  },
  description:
    "Register free and receive a permanent KAFRIADA ID with a QR profile any club or scout can check. Jigawa State pilot.",
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // maximumScale is deliberately not set. Preventing zoom on a page where
  // people read a 24-character identifier off a small screen would be a
  // cruelty, and it fails WCAG.
  themeColor: "#0E4429",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-NG">
      <body>
        <a className="skip-link" href="#main">Skip to content</a>
        <div className="shell">
          <header className="masthead">
            <Link href="/" className="wordmark">
              KAF<span>RIADA</span>
            </Link>
            <p className="masthead__meta">Jigawa State · Pilot</p>
          </header>
          <main id="main">{children}</main>
        </div>
      </body>
    </html>
  );
}

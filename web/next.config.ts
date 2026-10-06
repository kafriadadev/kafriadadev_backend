import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// Strings live in messages/<locale>.json; src/i18n/request.ts picks the locale.
const withNextIntl = createNextIntlPlugin();

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

  // The container image runs .next/standalone/server.js, which carries only the
  // node_modules actually reached at runtime. Harmless locally: `next start`
  // still serves the same build.
  output: "standalone",
  // Server-side image fonts and the logo, read from disk by /og/[kuid].
  outputFileTracingIncludes: {
    "/og/[kuid]": ["./assets/fonts/**", "./public/brand/kafriada-net-horizontal.svg"],
  },

  // Every launch screen must work with JavaScript disabled: Opera Mini in proxy
  // mode is common in northern Nigeria and runs almost none. Server Components
  // and server actions give us that for free, and this keeps us honest about it.
  // A photograph is up to 10MB and, with JavaScript off, arrives as a plain form POST
  // to a server action; the default limit (1MB) would refuse every phone camera.
  experimental: {
    optimizePackageImports: [],
    serverActions: { bodySizeLimit: "12mb" },
  },

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          // NOT "no-referrer". Under no-referrer Chromium sends `Origin: null` on
          // a plain form POST, Next's server-action CSRF check cannot parse it,
          // and registration returns 500 — but only with JavaScript off, because
          // the fetch-based path always sends a real Origin. That is precisely
          // the path this tier exists to protect, and it failed silently.
          // same-origin keeps the privacy intent (no KUID or QR signature in a
          // Referer to Google Fonts or any outbound link) and still lets
          // same-origin form posts identify themselves.
          { key: "Referrer-Policy", value: "same-origin" },
          {
            key: "Permissions-Policy",
            value: "geolocation=(), camera=(), microphone=(), payment=()",
          },
        ],
      },
    ];
  },
};

export default withNextIntl(config);

import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

  // Every launch screen must work with JavaScript disabled: Opera Mini in proxy
  // mode is common in northern Nigeria and runs almost none. Server Components
  // and server actions give us that for free, and this keeps us honest about it.
  experimental: { optimizePackageImports: [] },

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

export default config;

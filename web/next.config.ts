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
          { key: "Referrer-Policy", value: "no-referrer" },
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

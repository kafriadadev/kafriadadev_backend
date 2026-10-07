import { NextResponse, type NextRequest } from "next/server";

/**
 * Hands the requested path to server components as `x-kaf-path`, so a page
 * that cannot reach the API can send the person to /unavailable with a link
 * straight back to where they were. Nothing else.
 */
export function middleware(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.set("x-kaf-path", `${request.nextUrl.pathname}${request.nextUrl.search}`);
  return NextResponse.next({ request: { headers } });
}

export const config = {
  // Pages only: not static files, images, the API proxies' binary routes, or Next internals.
  matcher: ["/((?!_next/|brand/|icons/|sw\\.js|manifest|favicon|qr/|photo/|og/|card/[^/]+/card\\.|review-media/).*)"],
};

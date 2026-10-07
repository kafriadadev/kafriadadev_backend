/**
 * The cross-site check Next applies to server actions, for route handlers that
 * take form posts. A request with no Origin is let through, as Next does: old
 * browsers and some proxies (Opera Mini among them) send none, and the session
 * cookie is SameSite=Lax, so another site cannot post with it attached. An
 * Origin that names another host, or cannot be read, is refused.
 */
export function crossSite(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  try {
    return new URL(origin).host !== host;
  } catch {
    return true;
  }
}

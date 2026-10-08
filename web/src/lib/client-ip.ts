/**
 * The visitor's real address, read from whatever the edge in front of this site
 * reports it in. The API counts sign-in and registration attempts per address, so
 * this must be the visitor's, never this server's, or every visitor shares one
 * allowance.
 *
 * CLIENT_IP_HEADER names the edge:
 *   cf-connecting-ip  (default) Cloudflare in front: it sets this header itself.
 *   x-forwarded-for   Render, Railway, Fly and most load balancers: they append the
 *                     address that connected to them, so the rightmost public entry
 *                     is the visitor's; anything to its left the visitor could type.
 *   x-real-ip         An nginx-style proxy that sets it.
 * A header this site's own edge does not set is never read: the visitor could
 * write anything in it.
 */
import { isIP } from "node:net";

type Get = (name: string) => string | null | undefined;

const PRIVATE = [/^10\./, /^127\./, /^169\.254\./, /^192\.168\./, /^172\.(1[6-9]|2\d|3[01])\./, /^::1$/, /^f[cd][0-9a-f]{2}:/i, /^fe80:/i];

function isPublic(address: string): boolean {
  return isIP(address) !== 0 && !PRIVATE.some((re) => re.test(address));
}

export function clientAddress(get: Get): string | undefined {
  const mode = (process.env.CLIENT_IP_HEADER ?? "cf-connecting-ip").toLowerCase();
  if (mode === "x-forwarded-for") {
    const hops = (get("x-forwarded-for") ?? "").split(",").map((h) => h.trim()).filter(Boolean);
    for (let i = hops.length - 1; i >= 0; i--) if (isPublic(hops[i])) return hops[i];
    return undefined;
  }
  const value = get(mode)?.split(",")[0]?.trim();
  return value && isIP(value) !== 0 ? value : undefined;
}

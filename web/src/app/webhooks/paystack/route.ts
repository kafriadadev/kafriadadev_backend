import { API_BASE, INTERNAL_KEY, INTERNAL_KEY_HEADER } from "@/lib/api";
import { clientAddress } from "@/lib/client-ip";

export const dynamic = "force-dynamic";

const LIMIT_BYTES = 64 * 1024;

/**
 * Paystack's webhook, passed to the API untouched. The API is not on the
 * internet, so this is the public door Paystack knocks on. The body goes through
 * byte for byte, because the API checks Paystack's HMAC signature over the exact
 * bytes; this route checks nothing itself and decides nothing. Whatever the API
 * answers is what Paystack is told, so a failure here makes Paystack try again.
 *
 * Set Paystack's webhook URL to https://<this site>/webhooks/paystack.
 */
export async function POST(request: Request) {
  const body = await request.arrayBuffer();
  if (body.byteLength > LIMIT_BYTES) return new Response(null, { status: 413 });

  const headers: Record<string, string> = {
    "content-type": request.headers.get("content-type") ?? "application/json",
  };
  const signature = request.headers.get("x-paystack-signature");
  if (signature) headers["x-paystack-signature"] = signature;
  if (INTERNAL_KEY) headers[INTERNAL_KEY_HEADER] = INTERNAL_KEY;
  const ip = clientAddress((name) => request.headers.get(name));
  if (ip) headers["x-real-ip"] = ip;

  try {
    const upstream = await fetch(`${API_BASE}/v1/payments/webhook/paystack`, {
      method: "POST",
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
    return new Response(null, { status: upstream.status });
  } catch {
    // The API could not be reached: a 5xx makes Paystack deliver again later.
    return new Response(null, { status: 502 });
  }
}

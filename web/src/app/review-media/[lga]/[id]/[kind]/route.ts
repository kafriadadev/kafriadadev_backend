import { getImage } from "@/lib/api";
import { sessionToken } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * The photo or document a reviewer is deciding on.
 *
 * Only ever the safe copy, only for someone the API says may review this LGA, and
 * never cached anywhere — an identity document must not sit in a shared proxy. The
 * session cookie rides along on a plain <img>, so this works with JavaScript off.
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ lga: string; id: string; kind: string }> },
) {
  const token = await sessionToken();
  if (!token) return new Response("Sign in to continue.", { status: 401 });

  const { lga, id, kind } = await params;
  const upstream = await getImage(
    `/v1/lgas/${encodeURIComponent(lga)}/verification/${encodeURIComponent(id)}/media/${encodeURIComponent(kind)}`,
    token,
  );
  if (!upstream) return new Response("Not found", { status: 404 });
  return new Response(upstream.body, {
    headers: {
      "content-type": "image/jpeg",
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

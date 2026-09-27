import { getImage } from "@/lib/api";
import { sessionToken } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * The document a reviewer is deciding on for one club.
 *
 * Only the safe copy, only for someone the API says may review clubs, only while the
 * request is waiting for a decision, and never cached. The session cookie rides along
 * on a plain <img>, so it works with JavaScript off.
 */
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const token = await sessionToken();
  if (!token) return new Response("Sign in to continue.", { status: 401 });

  const { id } = await params;
  const upstream = await getImage(
    `/v1/admin/club-verification/${encodeURIComponent(id)}/document`,
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

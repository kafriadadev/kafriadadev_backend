import { getImage } from "@/lib/api";
import { sessionToken } from "@/lib/session";

export const dynamic = "force-dynamic";

/** A club photo, for someone the API says may review clubs. Never cached. */
export async function GET(_request: Request, { params }: { params: Promise<{ id: string; media: string }> }) {
  const token = await sessionToken();
  if (!token) return new Response("Sign in to continue.", { status: 401 });
  const { id, media } = await params;
  const upstream = await getImage(
    `/v1/admin/club-stage-three/${encodeURIComponent(id)}/photos/${encodeURIComponent(media)}`,
    token,
  );
  if (!upstream) return new Response("Not found", { status: 404 });
  return new Response(upstream.body, {
    headers: { "content-type": "image/jpeg", "cache-control": "private, no-store", "x-content-type-options": "nosniff" },
  });
}

import { getImage } from "@/lib/api";
import { sessionToken } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * A club photo, for the club's own administrators. Only the re-encoded copy, only for
 * someone the API says administers the club, never cached. Works on a plain <img>.
 */
export async function GET(_request: Request, { params }: { params: Promise<{ id: string; media: string }> }) {
  const token = await sessionToken();
  if (!token) return new Response("Sign in to continue.", { status: 401 });
  const { id, media } = await params;
  const upstream = await getImage(
    `/v1/clubs/${encodeURIComponent(id)}/stage-three/photos/${encodeURIComponent(media)}`,
    token,
  );
  if (!upstream) return new Response("Not found", { status: 404 });
  return new Response(upstream.body, {
    headers: { "content-type": "image/jpeg", "cache-control": "private, no-store", "x-content-type-options": "nosniff" },
  });
}

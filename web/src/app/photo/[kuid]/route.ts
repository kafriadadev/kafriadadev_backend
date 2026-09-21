import { getImage } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * An approved athlete's photograph, and nothing else.
 *
 * The browser never sees where photographs are kept. It asks this address, which
 * asks the API, which answers only for an athlete whose verification is currently
 * approved — so a withdrawn badge stops showing its photo within a minute, and a
 * guessed address for anyone unverified is a plain 404.
 */
export async function GET(_request: Request, { params }: { params: Promise<{ kuid: string }> }) {
  const { kuid } = await params;
  const upstream = await getImage(`/v1/public/athletes/${encodeURIComponent(kuid)}/photo`);
  if (!upstream) return new Response("Not found", { status: 404 });
  return new Response(upstream.body, {
    headers: {
      "content-type": "image/jpeg",
      // Short, so a withdrawal is not held up by a cache.
      "cache-control": "public, max-age=60",
      "x-content-type-options": "nosniff",
    },
  });
}

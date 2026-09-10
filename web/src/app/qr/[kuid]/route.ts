import { getQrSvg } from "@/lib/api";

/**
 * Serves an athlete's QR code as an image.
 *
 * A proxy rather than a direct link, because the domain tier is not reachable
 * from a browser and must not become reachable merely so an image can load.
 * The signature inside the code is generated server-side with a key no browser
 * ever sees.
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ kuid: string }> },
) {
  const { kuid } = await params;
  const svg = await getQrSvg(kuid);

  if (!svg) return new Response("Not found", { status: 404 });

  return new Response(svg, {
    headers: {
      "content-type": "image/svg+xml; charset=utf-8",
      // A KUID's QR never changes, so it can be cached hard. This matters on
      // 2G, where a repeat visit should cost nothing.
      "cache-control": "public, max-age=86400, stale-while-revalidate=604800",
      "x-content-type-options": "nosniff",
    },
  });
}

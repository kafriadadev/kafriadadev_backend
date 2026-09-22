import { getCardFile } from "@/lib/api";

/**
 * Serves the wallet card as a PNG, proxied the same way the QR code is
 * (see ../../../qr/[kuid]/route.ts) — the domain tier is not reachable from a
 * browser, so this is the only address a download link can point at.
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ kuid: string }> },
) {
  const { kuid } = await params;
  const png = await getCardFile(kuid, "png");
  if (!png) return new Response("Not found", { status: 404 });

  return new Response(png, {
    headers: {
      "content-type": "image/png",
      "content-disposition": `attachment; filename="${kuid}.png"`,
      "cache-control": "public, max-age=86400, stale-while-revalidate=604800",
      "x-content-type-options": "nosniff",
    },
  });
}

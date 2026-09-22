import { getCardFile } from "@/lib/api";

/** Serves the wallet card as a one-page PDF. See card.png/route.ts. */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ kuid: string }> },
) {
  const { kuid } = await params;
  const pdf = await getCardFile(kuid, "pdf");
  if (!pdf) return new Response("Not found", { status: 404 });

  return new Response(pdf, {
    headers: {
      "content-type": "application/pdf",
      "content-disposition": `attachment; filename="${kuid}.pdf"`,
      "cache-control": "public, max-age=86400, stale-while-revalidate=604800",
      "x-content-type-options": "nosniff",
    },
  });
}

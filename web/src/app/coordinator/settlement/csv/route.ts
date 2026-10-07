import { getSettlementCsv } from "@/lib/api";
import { sessionToken } from "@/lib/session";

export const dynamic = "force-dynamic";

/** The settlement lines as CSV, for someone the API says may read this LGA's payments. Never cached. */
export async function GET(request: Request) {
  const token = await sessionToken();
  if (!token) return new Response("Sign in to continue.", { status: 401 });

  const url = new URL(request.url);
  const lga = url.searchParams.get("lga") ?? "";
  const upstream = await getSettlementCsv(token, lga, {
    since: url.searchParams.get("since") ?? "",
    until: url.searchParams.get("until") ?? "",
    mine: url.searchParams.get("mine") !== "false",
  });
  if (!upstream) return new Response("No report for these dates.", { status: 404 });
  return new Response(upstream.body, {
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": upstream.headers.get("content-disposition") ?? `attachment; filename="settlement-${lga}.csv"`,
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

import { getCardSheets } from "@/lib/api";
import { sessionToken } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * One page of the batch as A4 sheets. Only for someone the API says coordinates this LGA,
 * and never cached: it is a stack of named cards. Drawing forty of them takes a few
 * seconds, so the request is given a long deadline.
 */
export async function GET(request: Request) {
  const token = await sessionToken();
  if (!token) return new Response("Sign in to continue.", { status: 401 });

  const url = new URL(request.url);
  const lga = url.searchParams.get("lga") ?? "";
  const upstream = await getCardSheets(token, lga, {
    since: url.searchParams.get("since") ?? "",
    until: url.searchParams.get("until") ?? "",
    unprinted: url.searchParams.get("unprinted") !== "false",
    page: Math.max(Number.parseInt(url.searchParams.get("page") ?? "1", 10) || 1, 1),
  });
  if (!upstream) return new Response("No cards match.", { status: 404 });
  return new Response(upstream.body, {
    headers: {
      "content-type": "application/pdf",
      "content-disposition": `attachment; filename="cards-${lga}.pdf"`,
      "cache-control": "private, no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

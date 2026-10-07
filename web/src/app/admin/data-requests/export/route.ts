import { ApiError, exportPersonData } from "@/lib/api";
import { crossSite } from "@/lib/same-origin";
import { clientMeta, sessionToken } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * ADM-07 export, as a plain form POST that answers with a file. A route handler
 * rather than a server action because an action cannot return a download. It
 * gets no automatic cross-site check, so it makes the one Next makes for actions.
 */
export async function POST(request: Request) {
  if (crossSite(request)) return new Response("Refused.", { status: 403 });
  const token = await sessionToken();
  if (!token) return Response.redirect(new URL("/sign-in", request.url), 303);

  const form = await request.formData();
  const userId = String(form.get("user_id") ?? "");
  const q = String(form.get("q") ?? "");
  try {
    const data = await exportPersonData(
      token, userId, String(form.get("received_via") ?? ""), String(form.get("note") ?? "").trim(), await clientMeta(),
    );
    const name = String((data.athlete as { kuid?: string } | null)?.kuid ?? userId);
    return new Response(JSON.stringify(data, null, 2), {
      headers: {
        "content-type": "application/json; charset=utf-8",
        "content-disposition": `attachment; filename="kafriada-net-data-${name}.json"`,
        "cache-control": "private, no-store",
        "x-content-type-options": "nosniff",
      },
    });
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    const back = new URL(`/admin/data-requests?${new URLSearchParams({ q, error: error.message })}`, request.url);
    return Response.redirect(back, 303);
  }
}

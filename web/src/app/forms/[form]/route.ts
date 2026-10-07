import { isRedirectError } from "next/dist/client/components/redirect-error";
import { getURLFromRedirectError } from "next/dist/client/components/redirect";

import { signInAction } from "@/app/sign-in/actions";
import { registerAthlete } from "@/app/register/actions";
import { crossSite } from "@/lib/same-origin";

export const dynamic = "force-dynamic";

/**
 * Where the zero-JavaScript public pages post their forms. Those pages live on
 * the Pages Router, which has no server actions, so each form posts here and
 * this runs the very same action. An action finishes by redirecting; that is
 * turned into a 303, so the browser follows it with a GET, as after any form.
 * Cookies the action set travel on that response.
 *
 * A server action is protected from cross-site posts by Next itself; a route
 * handler is not, so the same check is made here.
 */
const ACTIONS: Record<string, (form: FormData) => Promise<void>> = {
  "sign-in": signInAction,
  register: registerAthlete,
};

export async function POST(request: Request, { params }: { params: Promise<{ form: string }> }) {
  const action = ACTIONS[(await params).form];
  if (!action) return new Response("Not found.", { status: 404 });

  if (crossSite(request)) return new Response("Refused.", { status: 403 });

  try {
    await action(await request.formData());
  } catch (error) {
    if (isRedirectError(error)) {
      return new Response(null, { status: 303, headers: { location: getURLFromRedirectError(error) } });
    }
    throw error;
  }
  // Every action redirects; reaching here would be a bug, so fail closed.
  return new Response("No outcome.", { status: 500 });
}

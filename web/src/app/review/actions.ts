"use server";

import { redirect } from "next/navigation";

import { ApiError, decideCase } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/**
 * Approve or reject one case (CRD-02), as a plain form POST.
 *
 * Nothing here decides whether the reviewer MAY: the API refuses their own record,
 * another LGA's case, a case that is no longer waiting, and a rejection with no
 * reason. This only carries the decision there and reports what came back.
 */
export async function decideAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  const lga = String(formData.get("lga") ?? "");
  const id = String(formData.get("id") ?? "");
  const decision = String(formData.get("decision") ?? "");
  const reason = String(formData.get("reason") ?? "");
  const back = (extra: Record<string, string>) =>
    `/review?${new URLSearchParams({ lga, ...extra }).toString()}`;

  if (!lga || !id) redirect("/review");
  if (decision === "reject" && !reason.trim()) {
    redirect(back({ error: "Say what is wrong, so the athlete can fix it." }));
  }

  let outcome: string;
  try {
    const result = await decideCase(
      token,
      lga,
      id,
      decision === "approve" ? { approve: true } : { reject: reason },
      await clientMeta(),
    );
    outcome = result.outcome;
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(back({ error: error.message }));
    }
    throw error;
  }
  redirect(back({ done: outcome }));
}

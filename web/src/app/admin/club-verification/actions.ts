"use server";

import { redirect } from "next/navigation";

import { ApiError, decideClubVerification } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/** Approve or reject a club's verification, as plain form posts. A rejection needs a reason. */
export async function decideAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const club = String(formData.get("club") ?? "");
  const decision = formData.get("decision") === "reject" ? "reject" : "approve";
  const reason = String(formData.get("reason") ?? "").trim();

  if (decision === "reject" && !reason) {
    redirect(`/admin/club-verification?${new URLSearchParams({ error: "Say why. The club reads it as written." })}`);
  }
  try {
    await decideClubVerification(token, club, decision, reason, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(`/admin/club-verification?${new URLSearchParams({ error: error.message })}`);
    }
    throw error;
  }
  redirect(`/admin/club-verification?${new URLSearchParams({ done: decision === "approve" ? "approved" : "rejected" })}`);
}

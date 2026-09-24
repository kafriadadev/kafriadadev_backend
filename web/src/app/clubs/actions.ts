"use server";

import { redirect } from "next/navigation";

import { ApiError, answerInvitation } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/**
 * Accept or decline an invitation (ATH-05), as a plain form post. The API only ever
 * lets a person answer their own invitations; this carries the choice there.
 */
export async function answerAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const roster = String(formData.get("roster") ?? "");
  const answer = formData.get("answer") === "accept" ? "accept" : "decline";

  try {
    await answerInvitation(token, roster, answer, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(`/clubs?${new URLSearchParams({ error: error.message })}`);
    }
    throw error;
  }
  redirect(`/clubs?done=${answer}`);
}

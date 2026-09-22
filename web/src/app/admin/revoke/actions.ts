"use server";

import { redirect } from "next/navigation";

import { ApiError, revokeVerification } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/**
 * Withdraw a verification (ADM-03), as a plain form POST.
 *
 * Nothing here decides whether the actor MAY: the API re-checks the password,
 * refuses a request that is not currently approved, and requires a reason.
 * This only carries the form to it and reports what came back.
 */
export async function revokeAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  const requestId = String(formData.get("request_id") ?? "");
  const kuid = String(formData.get("kuid") ?? "");
  const reason = String(formData.get("reason") ?? "").trim();
  const currentPassword = String(formData.get("current_password") ?? "");

  const bounceBack = (message: string): never => {
    redirect(`/admin/revoke?${new URLSearchParams({ kuid, error: message })}`);
  };

  if (!requestId || !kuid) redirect("/admin/revoke");
  if (!reason) bounceBack("Say why this is being withdrawn.");
  if (!currentPassword) bounceBack("Enter your password to confirm.");

  try {
    await revokeVerification(token, requestId, reason, currentPassword, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) bounceBack(error.message);
    throw error;
  }

  redirect(`/admin/revoke?${new URLSearchParams({ done: kuid })}`);
}

"use server";

import { redirect } from "next/navigation";

import { ApiError, revokeClubVerification } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/**
 * Withdraw a club's verified badge, as a plain form POST.
 *
 * Nothing here decides whether this may happen: the API re-checks the password,
 * refuses a club that is not currently verified, and requires a reason. This only
 * carries the form to it and reports what came back.
 */
export async function revokeClubAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  const club = String(formData.get("club") ?? "");
  const reason = String(formData.get("reason") ?? "").trim();
  const currentPassword = String(formData.get("current_password") ?? "");
  const back = `/admin/clubs/${encodeURIComponent(club)}/revoke`;

  if (!reason) redirect(`${back}?${new URLSearchParams({ error: "Say why this is being withdrawn." })}`);
  if (!currentPassword) redirect(`${back}?${new URLSearchParams({ error: "Enter your password to confirm." })}`);

  try {
    await revokeClubVerification(token, club, reason, currentPassword, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(`${back}?${new URLSearchParams({ error: error.message })}`);
    }
    throw error;
  }
  redirect(`/admin/clubs?${new URLSearchParams({ done: "revoked" })}`);
}

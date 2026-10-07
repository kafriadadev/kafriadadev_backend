"use server";

import { redirect } from "next/navigation";

import { ApiError, setRollout } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/** Open or close one LGA (ADM-05). The API checks the password and records the reason. */
export async function rolloutAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  const lga = String(formData.get("lga") ?? "");
  const open = formData.get("open") === "true";
  const reason = String(formData.get("reason") ?? "").trim();
  const currentPassword = String(formData.get("current_password") ?? "");
  const bounceBack = (message: string): never => {
    redirect(`/admin/rollout?${new URLSearchParams({ lga, error: message })}`);
  };

  if (!lga) redirect("/admin/rollout");
  if (!reason) bounceBack("Say why. The reason is kept permanently.");
  if (!currentPassword) bounceBack("Enter your password to confirm.");

  let name = lga;
  try {
    name = (await setRollout(token, lga, open, reason, currentPassword, await clientMeta())).name;
  } catch (error) {
    if (error instanceof ApiError) bounceBack(error.message);
    throw error;
  }
  redirect(`/admin/rollout?${new URLSearchParams({ done: name, opened: String(open) })}`);
}

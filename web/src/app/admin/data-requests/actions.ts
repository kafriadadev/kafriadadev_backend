"use server";

import { redirect } from "next/navigation";

import { ApiError, erasePerson } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/** Erase one person (ADM-07). The API checks the password and refuses a second erasure. */
export async function eraseAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  const userId = String(formData.get("user_id") ?? "");
  const q = String(formData.get("q") ?? "");
  const receivedVia = String(formData.get("received_via") ?? "");
  const note = String(formData.get("note") ?? "").trim();
  const currentPassword = String(formData.get("current_password") ?? "");
  const bounceBack = (message: string): never => {
    redirect(`/admin/data-requests?${new URLSearchParams({ q, error: message })}#erase`);
  };

  if (!userId) redirect("/admin/data-requests");
  if (!note) bounceBack("Say who asked and how their identity was checked.");
  if (!currentPassword) bounceBack("Enter your password to confirm.");

  try {
    await erasePerson(token, userId, receivedVia, note, currentPassword, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) bounceBack(error.message);
    throw error;
  }
  redirect(`/admin/data-requests?${new URLSearchParams({ q, erased: "1" })}`);
}

"use server";

import { redirect } from "next/navigation";

import { ApiError, setClubStatus } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/** Approve or suspend a club, as a plain form post. The permission is the API's to check. */
export async function clubStatusAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const club = String(formData.get("club") ?? "");
  const change = formData.get("change") === "suspend" ? "suspend" : "approve";
  const status = String(formData.get("status") ?? "");
  const back = (params: Record<string, string>) =>
    `/admin/clubs?${new URLSearchParams({ ...(status ? { status } : {}), ...params })}`;

  try {
    await setClubStatus(token, club, change, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(back({ error: error.message }));
    }
    throw error;
  }
  redirect(back({ done: change === "approve" ? "approved" : "suspended" }));
}

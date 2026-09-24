"use server";

import { redirect } from "next/navigation";

import { ApiError, invitePlayer, removePlayer } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/**
 * Club roster actions, as plain form posts. Whether this person may act on this
 * club is the API's to decide from their own grants; nothing here checks it.
 */
export async function inviteAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const club = String(formData.get("club") ?? "");
  const kuid = String(formData.get("kuid") ?? "").trim();
  const back = `/clubs/${encodeURIComponent(club)}/invite`;

  try {
    await invitePlayer(token, club, kuid, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(`${back}?${new URLSearchParams({ q: kuid, error: error.message })}`);
    }
    throw error;
  }
  redirect(`/clubs/${encodeURIComponent(club)}?tab=invitations&invited=1`);
}

export async function removeAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const club = String(formData.get("club") ?? "");
  const roster = String(formData.get("roster") ?? "");
  const tab = String(formData.get("tab") ?? "roster");
  const base = `/clubs/${encodeURIComponent(club)}`;

  try {
    await removePlayer(token, club, roster, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(`${base}?${new URLSearchParams({ tab, error: error.message })}`);
    }
    throw error;
  }
  redirect(`${base}?${new URLSearchParams({ tab, removed: "1" })}`);
}

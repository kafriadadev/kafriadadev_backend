"use server";

import { redirect } from "next/navigation";

import { signOut } from "@/lib/api";
import { clientMeta, endSession, sessionToken } from "@/lib/session";

/** Sign out: end the session at the API, then drop the cookie. */
export async function signOutAction(): Promise<void> {
  const token = await sessionToken();
  if (token) {
    // If the API cannot be reached the cookie still goes, and the session dies
    // on its own idle clock. Keeping the person signed in because a network
    // call failed would be the wrong way round on a shared phone.
    await signOut(token, await clientMeta()).catch(() => undefined);
  }
  await endSession();
  redirect("/");
}

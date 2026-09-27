"use server";

import { redirect } from "next/navigation";

import { ApiError, markCardsPrinted } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/** Record that the cards on this page were printed. The API only touches the LGA's own athletes. */
export async function markPrintedAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const lga = String(formData.get("lga") ?? "");
  const kuids = String(formData.get("kuids") ?? "").split(",").filter(Boolean);
  const keep = new URLSearchParams();
  for (const key of ["lga", "since", "until", "unprinted", "page"]) {
    const value = String(formData.get(key) ?? "");
    if (value) keep.set(key, value);
  }

  let marked = 0;
  try {
    marked = (await markCardsPrinted(token, lga, kuids, await clientMeta())).marked;
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      keep.set("error", error.message);
      redirect(`/coordinator/cards?${keep}`);
    }
    throw error;
  }
  keep.set("marked", String(marked));
  redirect(`/coordinator/cards?${keep}`);
}

"use server";

import { redirect } from "next/navigation";

import {
  ApiError,
  resubmitClubVerification,
  startClubPayment,
  uploadClubDocument,
} from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/**
 * Club verification (CLB-04), as plain form posts. Whether this person may act on this
 * club, whether it is approved, and whether a document is ready to pay for are all the
 * API's to decide; these only carry the request there and back.
 */
const back = (club: string, params: Record<string, string> = {}): string =>
  `/clubs/${encodeURIComponent(club)}/verify${
    Object.keys(params).length ? `?${new URLSearchParams(params)}` : ""
  }`;

export async function uploadDocumentAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const club = String(formData.get("club") ?? "");
  const file = formData.get("document");
  if (!(file instanceof File) || file.size === 0) {
    redirect(back(club, { error: "Choose the document to add." }));
  }
  try {
    await uploadClubDocument(
      token,
      club,
      { type: (file as File).type, size: (file as File).size, bytes: await (file as File).arrayBuffer() },
      await clientMeta(),
    );
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(back(club, { error: error.message }));
    }
    throw error;
  }
  redirect(back(club, { saved: "1" }));
}

export async function startClubPaymentAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const club = String(formData.get("club") ?? "");
  let started;
  try {
    started = await startClubPayment(token, club, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(back(club, { error: error.message }));
    }
    throw error;
  }
  redirect(started.authorization_url);
}

export async function resubmitClubAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const club = String(formData.get("club") ?? "");
  try {
    await resubmitClubVerification(token, club, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(back(club, { error: error.message }));
    }
    throw error;
  }
  redirect(back(club));
}

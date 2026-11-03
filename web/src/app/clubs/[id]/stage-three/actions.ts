"use server";

import { redirect } from "next/navigation";

import {
  ApiError,
  removeClubPhoto,
  resubmitClubStage3,
  saveClubLinks,
  startClubStage3Payment,
  uploadClubPhoto,
} from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/**
 * Club stage three, as plain form posts. Whether this person may act on this club, its
 * stage, and whether the links and photos are enough to pay for are all the API's to
 * decide; these only carry the request there and back.
 */
const back = (club: string, params: Record<string, string> = {}): string =>
  `/clubs/${encodeURIComponent(club)}/stage-three${
    Object.keys(params).length ? `?${new URLSearchParams(params)}` : ""
  }`;

async function run(club: string, work: (token: string) => Promise<void>, done: Record<string, string> = {}): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  try {
    await work(token);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(back(club, { error: error.message }));
    }
    throw error;
  }
  redirect(back(club, done));
}

export async function saveLinksAction(formData: FormData): Promise<void> {
  const club = String(formData.get("club") ?? "");
  const links = formData.getAll("links").map((l) => String(l).trim()).filter(Boolean);
  await run(club, async (token) => saveClubLinks(token, club, links, await clientMeta()), { saved: "links" });
}

export async function uploadPhotoAction(formData: FormData): Promise<void> {
  const club = String(formData.get("club") ?? "");
  const file = formData.get("photo");
  if (!(file instanceof File) || file.size === 0) redirect(back(club, { error: "Choose a photo to add." }));
  const photo = file as File;
  await run(
    club,
    async (token) =>
      uploadClubPhoto(token, club, { type: photo.type, size: photo.size, bytes: await photo.arrayBuffer() }, await clientMeta()),
    { saved: "photo" },
  );
}

export async function removePhotoAction(formData: FormData): Promise<void> {
  const club = String(formData.get("club") ?? "");
  const media = String(formData.get("media") ?? "");
  await run(club, async (token) => removeClubPhoto(token, club, media, await clientMeta()));
}

export async function resubmitStage3Action(formData: FormData): Promise<void> {
  const club = String(formData.get("club") ?? "");
  await run(club, async (token) => resubmitClubStage3(token, club, await clientMeta()));
}

export async function startStage3PaymentAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const club = String(formData.get("club") ?? "");
  let started;
  try {
    started = await startClubStage3Payment(token, club, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(back(club, { error: error.message }));
    }
    throw error;
  }
  redirect(started.authorization_url);
}

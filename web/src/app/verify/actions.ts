"use server";

import { redirect } from "next/navigation";

import { ApiError, resubmitVerification, uploadFile } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

const KINDS = ["photo", "document"] as const;

/**
 * Add the photo and/or the document (VER-02), as a plain multipart form POST.
 *
 * With JavaScript off this is the only path there is: the bytes pass through here
 * and the API once, on their way to storage, and the API re-encodes them before
 * anyone can see them. Either file may be sent on its own, so a person on a slow
 * connection can add them one at a time.
 */
export async function uploadAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const meta = await clientMeta();

  let sent = 0;
  try {
    for (const kind of KINDS) {
      const file = formData.get(kind);
      if (!(file instanceof File) || file.size === 0) continue;
      await uploadFile(token, kind, { type: file.type, size: file.size, bytes: await file.arrayBuffer() }, meta);
      sent += 1;
    }
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(`/verify?error=${encodeURIComponent(error.message)}`);
    }
    throw error;
  }
  redirect(sent ? "/verify?saved=1" : `/verify?error=${encodeURIComponent("Choose a photo or a document to add.")}`);
}

/** Send a rejected verification back. The payment already made still covers it. */
export async function resubmitAction(): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  try {
    await resubmitVerification(token, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(`/verify?error=${encodeURIComponent(error.message)}`);
    }
    throw error;
  }
  redirect("/verify");
}

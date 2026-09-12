"use server";

import { redirect } from "next/navigation";

import { ApiError, signIn } from "@/lib/api";
import { clientMeta, startPending, startSession } from "@/lib/session";

/**
 * Sign-in (AUT-04), as a plain form POST, so it works with JavaScript off.
 *
 * On success the cookie is set on the redirect itself. On failure it goes back
 * to the form with the message and the phone number — never the password,
 * which is never put in a URL.
 */
export async function signInAction(formData: FormData): Promise<void> {
  const phone = String(formData.get("phone") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  const bounceBack = (message: string): never => {
    const params = new URLSearchParams({ error: message });
    if (phone) params.set("phone", phone);
    redirect(`/sign-in?${params.toString()}`);
  };

  if (!phone || !password) bounceBack("Enter your phone number and your password.");

  let session;
  try {
    session = await signIn({ phone, password }, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) bounceBack(error.message);
    throw error;
  }

  await startSession(session.token, {
    isStaff: session.is_staff,
    absoluteExpiresAt: session.absolute_expires_at,
  });
  // AUT-04: a number that was never confirmed goes straight to AUT-02.
  if (!session.phone_verified) {
    await startPending({ phone, kuid: "" });
    redirect("/register/confirm");
  }
  redirect("/me");
}

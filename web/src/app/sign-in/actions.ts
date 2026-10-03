"use server";

import { redirect } from "next/navigation";

import { ApiError, signIn } from "@/lib/api";
import { clientMeta, startPending, startSession } from "@/lib/session";

/**
 * Sign-in (AUT-04), as a plain form POST, so it works with JavaScript off.
 *
 * On success the cookie is set on the redirect itself. An account whose email is
 * not confirmed gets no session: it goes to the confirm screen, where a fresh code
 * is waiting. One with no email at all comes back here to add one. On failure it
 * goes back to the form with the message and the phone number, never the password.
 */
export async function signInAction(formData: FormData): Promise<void> {
  const phone = String(formData.get("phone") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const email = String(formData.get("email") ?? "").trim();

  const bounceBack = (message: string, extra: Record<string, string> = {}): never => {
    const params = new URLSearchParams({ error: message, ...extra });
    if (phone) params.set("phone", phone);
    redirect(`/sign-in?${params.toString()}`);
  };

  if (!phone || !password) bounceBack("Enter your phone number and your password.");

  let session;
  try {
    session = await signIn({ phone, password, ...(email ? { email } : {}) }, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.reason === "email_unconfirmed") {
        await startPending({
          phone,
          kuid: "",
          email: String(error.detail?.email_masked ?? ""),
        });
        redirect("/register/confirm");
      }
      if (error.reason === "email_missing" || error.field === "email") {
        bounceBack(error.message, { need_email: "1" });
      }
      bounceBack(error.message);
    }
    throw error;
  }

  await startSession(session.token, {
    isStaff: session.is_staff,
    absoluteExpiresAt: session.absolute_expires_at,
  });
  redirect("/me");
}

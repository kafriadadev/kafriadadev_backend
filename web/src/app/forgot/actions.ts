"use server";

import { redirect } from "next/navigation";

import { ApiError, resetPassword, sendResetCode } from "@/lib/api";
import { clientMeta } from "@/lib/session";

/**
 * Password reset (AUT-05), in two plain POSTs.
 *
 * An unknown number gets exactly the same screen as a registered one. Anything
 * else turns this form into a way of asking whether somebody is registered with
 * KAFRIADA — which the privacy notice promises it is not.
 */
export async function sendResetCodeAction(formData: FormData): Promise<void> {
  const phone = String(formData.get("phone") ?? "").trim();
  if (!phone) {
    redirect(`/forgot?${new URLSearchParams({ error: "Enter your phone number." })}`);
  }

  try {
    await sendResetCode(phone, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      redirect(`/forgot?${new URLSearchParams({ error: error.message, phone })}`);
    }
    throw error;
  }
  redirect(`/forgot?${new URLSearchParams({ sent: "1", phone })}`);
}

export async function resetPasswordAction(formData: FormData): Promise<void> {
  const phone = String(formData.get("phone") ?? "").trim();
  const code = String(formData.get("code") ?? "").trim();
  const password = String(formData.get("new_password") ?? "");

  const bounceBack = (message: string): never => {
    // The new password is never put in a URL, the same rule as registration.
    redirect(`/forgot?${new URLSearchParams({ sent: "1", phone, error: message })}`);
  };

  if (!code) bounceBack("Enter the code from the text message.");
  if (!password) bounceBack("Choose a new password.");

  try {
    await resetPassword({ phone, code, new_password: password }, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) bounceBack(error.message);
    throw error;
  }
  redirect("/sign-in?reset=1");
}

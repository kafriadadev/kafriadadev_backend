"use server";

import { redirect } from "next/navigation";

import { ApiError, confirmEmail, sendEmailCode } from "@/lib/api";
import { clientMeta, endPending, pending, startSession } from "@/lib/session";

/**
 * Confirm the email address with its code, as a plain form POST.
 *
 * A correct code confirms the address and signs the person in. Until it is
 * confirmed there is no session at all, so this is the only way in.
 */
export async function confirmEmailAction(formData: FormData): Promise<void> {
  const code = String(formData.get("code") ?? "").trim();
  const phone = (await pending())?.phone;

  const bounceBack = (message: string): never => {
    redirect(`/register/confirm?${new URLSearchParams({ error: message })}`);
  };

  if (!phone) redirect("/sign-in");
  if (!code) bounceBack("Enter the 6-digit code.");

  let confirmed;
  try {
    confirmed = await confirmEmail({ phone, code }, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) bounceBack(error.message);
    throw error;
  }

  await startSession(confirmed.token, {
    isStaff: confirmed.is_staff,
    absoluteExpiresAt: confirmed.absolute_expires_at,
  });
  await endPending();
  redirect("/me?welcome=1");
}

/** Send another code. The answer never says whether one was actually sent. */
export async function resendCodeAction(): Promise<void> {
  const phone = (await pending())?.phone;
  if (!phone) redirect("/sign-in");

  let sent;
  try {
    sent = await sendEmailCode(phone, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      redirect(`/register/confirm?${new URLSearchParams({ error: error.message })}`);
    }
    throw error;
  }

  const params = new URLSearchParams(
    sent.daily_limit_reached
      ? { error: "That is all the codes we can send today. Please try again tomorrow." }
      : { sent: "1", wait: String(sent.resend_in) },
  );
  redirect(`/register/confirm?${params.toString()}`);
}

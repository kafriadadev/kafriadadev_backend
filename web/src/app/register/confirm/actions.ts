"use server";

import { redirect } from "next/navigation";

import { ApiError, confirmPhone, sendPhoneCode } from "@/lib/api";
import { clientMeta, endPending, pending, startSession } from "@/lib/session";

/**
 * Confirm the phone number (AUT-02), as a plain form POST.
 *
 * A correct code confirms the number and signs the person in — holding the
 * phone is exactly what a session is meant to prove — and lands them on their
 * card, which already existed before the code was ever sent.
 */
export async function confirmPhoneAction(formData: FormData): Promise<void> {
  const code = String(formData.get("code") ?? "").trim();
  const phone = String(formData.get("phone") ?? "").trim() || (await pending())?.phone;

  const bounceBack = (message: string): never => {
    redirect(`/register/confirm?${new URLSearchParams({ error: message })}`);
  };

  if (!phone) redirect("/sign-in");
  if (!code) bounceBack("Enter the 6-digit code.");

  let confirmed;
  try {
    confirmed = await confirmPhone({ phone, code }, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) bounceBack(error.message);
    throw error;
  }

  await startSession(confirmed.token, {
    isStaff: confirmed.is_staff,
    absoluteExpiresAt: confirmed.absolute_expires_at,
  });
  await endPending();
  redirect(confirmed.kuid ? `/card/${encodeURIComponent(confirmed.kuid)}` : "/me");
}

/** Send another code. The answer never says whether one was actually sent. */
export async function resendCodeAction(formData: FormData): Promise<void> {
  const phone = String(formData.get("phone") ?? "").trim() || (await pending())?.phone;
  if (!phone) redirect("/sign-in");

  let sent;
  try {
    sent = await sendPhoneCode(phone, await clientMeta());
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

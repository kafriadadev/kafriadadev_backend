"use server";

import { redirect } from "next/navigation";

import { ApiError, recordReversal } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/** Naira, as typed, to whole kobo. Null for anything that is not a plain amount. */
function toKobo(naira: string): number | null {
  const match = naira.trim().match(/^(\d+)(?:\.(\d{1,2}))?$/);
  if (!match) return null;
  const whole = Number.parseInt(match[1], 10);
  const cents = Number.parseInt((match[2] ?? "0").padEnd(2, "0"), 10);
  const kobo = whole * 100 + cents;
  return kobo > 0 ? kobo : null;
}

/**
 * Record a refund (ADM-04), as a plain form POST.
 *
 * Nothing here decides whether the actor MAY: the API re-checks the password,
 * refuses a payment that is not settled or already has a refund, and caps the
 * amount at what was actually paid. This only carries the form to it.
 */
export async function reverseAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  const reference = String(formData.get("reference") ?? "");
  const amountNaira = String(formData.get("amount_naira") ?? "");
  const reason = String(formData.get("reason") ?? "").trim();
  const currentPassword = String(formData.get("current_password") ?? "");

  const bounceBack = (message: string): never => {
    redirect(`/admin/reversal?${new URLSearchParams({ reference, error: message })}`);
  };

  if (!reference) redirect("/admin/reversal");
  const parsedKobo = toKobo(amountNaira);
  if (parsedKobo === null) return bounceBack("Enter the amount refunded, in naira.");
  const amountKobo: number = parsedKobo;
  if (!reason) bounceBack("Say why the refund was made.");
  if (!currentPassword) bounceBack("Enter your password to confirm.");

  try {
    await recordReversal(token, reference, amountKobo, reason, currentPassword, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) bounceBack(error.message);
    throw error;
  }

  redirect(`/admin/reversal?${new URLSearchParams({ done: reference })}`);
}

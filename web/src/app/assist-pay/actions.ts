"use server";

import { redirect } from "next/navigation";

import { ApiError, startPaymentOnBehalf } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/**
 * Start an assisted checkout (CRD-04), as a plain form POST.
 *
 * Nothing here decides whether the coordinator may: the API checks the LGA,
 * the athlete's readiness, whether they already paid, and the two daily caps.
 * This only carries the KUID to it and forwards to Paystack on success —
 * exactly the shape of the athlete's own /pay, one step earlier.
 */
export async function startAssistedPaymentAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  const lga = String(formData.get("lga") ?? "").trim();
  const kuid = String(formData.get("kuid") ?? "").trim();
  if (!lga) redirect("/assist-pay");

  const bounceBack = (message: string): never => {
    redirect(`/assist-pay?${new URLSearchParams({ lga, kuid, error: message })}`);
  };

  if (!kuid) bounceBack("Enter the athlete's KAFRIADA NET ID.");

  let started;
  try {
    started = await startPaymentOnBehalf(token, lga, kuid, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      bounceBack(error.message);
    }
    throw error;
  }
  redirect(started.authorization_url);
}

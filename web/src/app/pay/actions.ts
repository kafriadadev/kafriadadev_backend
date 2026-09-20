"use server";

import { redirect } from "next/navigation";

import { ApiError, startPayment } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/**
 * Leave for Paystack (VER-03), as a plain form POST so it works with JavaScript
 * off. The API creates the payment record first and returns the address to go
 * to; this only forwards the person there.
 *
 * Nothing on this side decides that anything was paid. When they come back the
 * screen reads our own record, which only the signed webhook can change.
 */
export async function startPaymentAction(): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let started;
  try {
    started = await startPayment(token, await clientMeta());
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      redirect(`/pay?error=${encodeURIComponent(error.message)}`);
    }
    throw error;
  }
  redirect(started.authorization_url);
}

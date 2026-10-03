"use server";

import { redirect } from "next/navigation";

import { ApiError, register } from "@/lib/api";
import { startPending } from "@/lib/session";

/** The fields bounced back to the form after a refusal. Never the password. */
const KEPT = [
  "first_name", "middle_name", "surname", "gender", "date_of_birth", "nationality",
  "state_of_origin", "phone", "email", "address_line", "town", "lga_id", "sport",
  "level_played", "playing_position", "secondary_position", "dominant_side",
  "years_experience", "height_cm", "weight_kg", "emergency_name",
  "emergency_relationship", "emergency_phone",
] as const;

/**
 * Registration, submitted as a plain form POST.
 *
 * **This must work with JavaScript switched off**, so the whole flow is a POST
 * followed by a redirect, the only pattern Opera Mini in proxy mode can be
 * relied on to complete.
 *
 * On success it goes to the screen that asks for the emailed code. On rejection it
 * goes back to the form with the message, the field to point at, and the values
 * already typed, **except the password, which is never put in a URL.** A URL ends
 * up in browser history, in server logs and on the screen of a shared phone.
 */
export async function registerAthlete(formData: FormData): Promise<void> {
  const text = (key: string): string => String(formData.get(key) ?? "").trim();
  const kept = Object.fromEntries(KEPT.map((k) => [k, text(k)])) as Record<
    (typeof KEPT)[number],
    string
  >;

  const bounceBack = (message: string, field?: string): never => {
    const params = new URLSearchParams({ error: message });
    if (field) params.set("field", field);
    for (const [key, value] of Object.entries(kept)) {
      if (value) params.set(key, value);
    }
    redirect(`/register?${params.toString()}`);
  };

  if (!formData.get("accept_privacy_notice")) {
    bounceBack(
      "Please confirm the declaration and accept the privacy notice.",
      "accept_privacy_notice",
    );
  }
  // Whole numbers only. Anything else is pointed at here rather than sent on.
  const whole = (key: "height_cm" | "weight_kg" | "years_experience", label: string): number => {
    const n = Number(kept[key]);
    if (!kept[key] || !Number.isInteger(n)) bounceBack(`Enter your ${label} as a whole number.`, key);
    return n;
  };
  const height = whole("height_cm", "height in centimetres");
  const weight = whole("weight_kg", "weight in kilograms");
  const years = whole("years_experience", "years playing");

  try {
    await register({
      ...kept,
      middle_name: kept.middle_name || null,
      secondary_position: kept.secondary_position || null,
      height_cm: height,
      weight_kg: weight,
      years_experience: years,
      password: String(formData.get("password") ?? ""),
      accept_privacy_notice: true,
    });
  } catch (error) {
    if (error instanceof ApiError) bounceBack(error.message, error.field);
    throw error;
  }

  await startPending({ phone: kept.phone, kuid: "", email: maskEmail(kept.email) });
  redirect("/register/confirm");
}

function maskEmail(email: string): string {
  const [local, domain] = email.toLowerCase().split("@");
  return `${(local ?? "").slice(0, 1)}***@${domain ?? ""}`;
}

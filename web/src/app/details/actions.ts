"use server";

import { redirect } from "next/navigation";

import { ApiError, updateMyAthleteDetails } from "@/lib/api";
import { sessionToken } from "@/lib/session";

/**
 * My details (ATH-02), as a plain form POST.
 *
 * The whole form is always submitted and every field except the two optional ones
 * is required. The API decides whether each value is allowed.
 */
export async function updateDetailsAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  const text = (key: string): string => String(formData.get(key) ?? "").trim();
  const bounce = (message: string, field?: string): never => {
    const params = new URLSearchParams({ error: message });
    if (field) params.set("field", field);
    redirect(`/details?${params.toString()}`);
  };
  const whole = (key: string, label: string): number => {
    const n = Number(text(key));
    if (!text(key) || !Number.isInteger(n)) bounce(`Enter ${label} as a whole number.`, key);
    return n;
  };

  try {
    await updateMyAthleteDetails(token, {
      playing_position: text("playing_position"),
      secondary_position: text("secondary_position") || null,
      dominant_side: text("dominant_side"),
      secondary_sport: text("secondary_sport") || null,
      years_experience: whole("years_experience", "years playing"),
      height_cm: whole("height_cm", "your height in centimetres"),
      weight_kg: whole("weight_kg", "your weight in kilograms"),
      level_played: text("level_played"),
      address_line: text("address_line"),
      town: text("town"),
      emergency_name: text("emergency_name"),
      emergency_relationship: text("emergency_relationship"),
      emergency_phone: text("emergency_phone"),
    });
  } catch (error) {
    if (error instanceof ApiError) bounce(error.message, error.field);
    throw error;
  }

  redirect("/details?saved=1");
}

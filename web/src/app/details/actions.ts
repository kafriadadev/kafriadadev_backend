"use server";

import { redirect } from "next/navigation";

import { ApiError, updateMyAthleteDetails } from "@/lib/api";
import { sessionToken } from "@/lib/session";

/** Blank input means "leave it unset", not "invalid" — every field is optional. */
function orNull(value: FormDataEntryValue | null): string | null {
  const text = String(value ?? "").trim();
  return text || null;
}

/**
 * Edit my details (ATH-02), as a plain form POST.
 *
 * Every field is optional and the whole form is always submitted, so a blank
 * box clears that field rather than leaving it unchanged. The API is what
 * decides whether a value is one of the allowed choices.
 */
export async function updateDetailsAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  const yearsRaw = orNull(formData.get("years_experience"));
  const years = yearsRaw === null ? null : Number.parseInt(yearsRaw, 10);

  try {
    await updateMyAthleteDetails(token, {
      gender: orNull(formData.get("gender")),
      dominant_side: orNull(formData.get("dominant_side")),
      secondary_sport: orNull(formData.get("secondary_sport")),
      years_experience: years !== null && Number.isFinite(years) ? years : null,
    });
  } catch (error) {
    if (error instanceof ApiError) {
      const params = new URLSearchParams({ error: error.message });
      if (error.field) params.set("field", error.field);
      redirect(`/details?${params.toString()}`);
    }
    throw error;
  }

  redirect("/details?saved=1");
}

"use server";

import { redirect } from "next/navigation";

import { ApiError, registerClub } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/**
 * Register a club (CLB-01), as a plain form POST.
 *
 * Every rule is the API's. This carries the typed values there and, on a refusal,
 * back to the form with the message, the field to point at, and what was typed. A
 * name that is already taken in the LGA comes back as a question the person can
 * answer with a tick, not as an error.
 */
export async function registerClubAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  const text = (name: string) => String(formData.get(name) ?? "").trim();
  const submitted = {
    name: text("name"),
    year_founded: text("year_founded"),
    lga_id: text("lga_id"),
    sport: text("sport"),
    contact_phone: text("contact_phone"),
  };

  const bounceBack = (message: string, field?: string, duplicate = false): never => {
    const params = new URLSearchParams({ error: message });
    if (field) params.set("field", field);
    if (duplicate) params.set("duplicate", "1");
    for (const [key, value] of Object.entries(submitted)) {
      if (value) params.set(key, value);
    }
    redirect(`/clubs/new?${params.toString()}`);
  };

  const year = submitted.year_founded ? Number.parseInt(submitted.year_founded, 10) : null;
  if (submitted.year_founded && (year === null || Number.isNaN(year))) {
    bounceBack("Enter a valid year.", "year_founded");
  }

  let made;
  try {
    made = await registerClub(
      token,
      {
        name: submitted.name,
        sport: submitted.sport,
        lga_id: submitted.lga_id,
        contact_phone: submitted.contact_phone,
        year_founded: year,
        confirm_duplicate: formData.get("confirm_duplicate") === "on",
      },
      await clientMeta(),
    );
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      bounceBack(error.message, error.field, error.status === 409);
    }
    throw error;
  }
  redirect(`/clubs/${encodeURIComponent(made.club_id)}?registered=1`);
}

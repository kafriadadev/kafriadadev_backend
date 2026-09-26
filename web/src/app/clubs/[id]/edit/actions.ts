"use server";

import { redirect } from "next/navigation";

import { ApiError, updateClub } from "@/lib/api";
import { clientMeta, sessionToken } from "@/lib/session";

/** Save a club's details as a plain form post. Every rule is the API's. */
export async function updateClubAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const club = String(formData.get("club") ?? "");
  const text = (name: string) => String(formData.get(name) ?? "").trim();
  const submitted = {
    name: text("name"),
    contact_phone: text("contact_phone"),
    year_founded: text("year_founded"),
  };

  const bounceBack = (message: string, field?: string): never => {
    const params = new URLSearchParams({ error: message });
    if (field) params.set("field", field);
    for (const [key, value] of Object.entries(submitted)) if (value) params.set(key, value);
    redirect(`/clubs/${encodeURIComponent(club)}/edit?${params}`);
  };

  const year = submitted.year_founded ? Number.parseInt(submitted.year_founded, 10) : null;
  if (submitted.year_founded && (year === null || Number.isNaN(year))) {
    bounceBack("Enter a valid year.", "year_founded");
  }

  try {
    await updateClub(
      token,
      club,
      { name: submitted.name, contact_phone: submitted.contact_phone, year_founded: year },
      await clientMeta(),
    );
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      bounceBack(error.message, error.field);
    }
    throw error;
  }
  redirect(`/clubs/${encodeURIComponent(club)}?tab=details&saved=1`);
}

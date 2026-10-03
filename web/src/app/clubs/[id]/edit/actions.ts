"use server";

import { redirect } from "next/navigation";

import { ApiError, updateClub } from "@/lib/api";
import { readClub } from "@/lib/clubProfile";
import { clientMeta, sessionToken } from "@/lib/session";

/** Save a club's record as a plain form post. Every rule is the API's. */
export async function updateClubAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const club = String(formData.get("club") ?? "");
  const read = readClub(formData);

  const bounceBack = (message: string, field?: string): never => {
    const params = new URLSearchParams(read.kept);
    params.set("error", message);
    params.set("edited", "1");
    if (field) params.set("field", field);
    redirect(`/clubs/${encodeURIComponent(club)}/edit?${params}`);
  };

  if (Number.isNaN(read.profile.year_founded)) {
    bounceBack("Enter the year the club was founded.", "year_founded");
  }

  try {
    await updateClub(
      token,
      club,
      { ...read.profile, name: read.name, contact_phone: read.contact_phone },
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

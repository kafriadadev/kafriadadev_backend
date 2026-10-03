"use server";

import { redirect } from "next/navigation";

import { ApiError, getMe, registerClub } from "@/lib/api";
import { readClub } from "@/lib/clubProfile";
import { clientMeta, sessionToken } from "@/lib/session";

/**
 * Staff register a club, as a plain form POST: an administrator in any area, a
 * coordinator in their own. They become its administrator. Every rule is the API's.
 */
export async function registerClubAction(formData: FormData): Promise<void> {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const read = readClub(formData);

  const bounceBack = (message: string, field?: string, duplicate = false): never => {
    const params = new URLSearchParams(read.kept);
    params.set("error", message);
    if (field) params.set("field", field);
    if (duplicate) params.set("duplicate", "1");
    redirect(`/clubs/new?${params.toString()}`);
  };

  if (Number.isNaN(read.profile.year_founded)) {
    bounceBack("Enter the year the club was founded.", "year_founded");
  }

  // A coordinator's club is registered in their own area, whatever the form says.
  const me = await getMe(token).catch(() => null);
  const isAdmin = me?.roles.some((r) => r.role === "super_admin") ?? false;
  const coordinatorLga = me?.roles.find((r) => r.role === "lga_coordinator")?.scope_id ?? undefined;

  let made;
  try {
    made = await registerClub(
      token,
      {
        ...read.profile,
        name: read.name,
        sport: read.sport,
        lga_id: read.lga_id,
        contact_phone: read.contact_phone,
        confirm_duplicate: formData.get("confirm_duplicate") === "on",
      } as Parameters<typeof registerClub>[1],
      await clientMeta(),
      isAdmin ? undefined : coordinatorLga,
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

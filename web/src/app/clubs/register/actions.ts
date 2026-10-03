"use server";

import { redirect } from "next/navigation";

import { ApiError, signUpClub } from "@/lib/api";
import { readClub } from "@/lib/clubProfile";
import { clientMeta, startPending } from "@/lib/session";

/**
 * A club signs itself up, as a plain form POST.
 *
 * On success the representative goes to the screen that asks for the code emailed
 * to them; the club reaches an administrator once that code is accepted. On a
 * refusal everything typed comes back, except the password.
 */
export async function signUpClubAction(formData: FormData): Promise<void> {
  const text = (k: string) => String(formData.get(k) ?? "").trim();
  const club = readClub(formData);
  const rep = {
    rep_first_name: text("rep_first_name"),
    rep_surname: text("rep_surname"),
    rep_role: text("rep_role"),
    rep_phone: text("rep_phone"),
    rep_email: text("rep_email"),
  };

  const bounceBack = (message: string, field?: string, duplicate = false): never => {
    const params = new URLSearchParams(club.kept);
    params.set("error", message);
    if (field) params.set("field", field);
    if (duplicate) params.set("duplicate", "1");
    for (const [k, v] of Object.entries(rep)) if (v) params.set(k, v);
    redirect(`/clubs/register?${params.toString()}`);
  };

  if (!formData.get("accept_privacy_notice")) {
    bounceBack("Please confirm the declaration and accept the privacy notice.",
      "accept_privacy_notice");
  }
  if (Number.isNaN(club.profile.year_founded)) {
    bounceBack("Enter the year the club was founded.", "year_founded");
  }

  let made;
  try {
    made = await signUpClub(
      {
        ...club.profile,
        name: club.name,
        sport: club.sport,
        lga_id: club.lga_id,
        contact_phone: club.contact_phone,
        confirm_duplicate: formData.get("confirm_duplicate") === "on",
        ...rep,
        password: String(formData.get("password") ?? ""),
        accept_privacy_notice: true,
      } as Parameters<typeof signUpClub>[0],
      await clientMeta(),
    );
  } catch (error) {
    if (error instanceof ApiError) bounceBack(error.message, error.field, error.status === 409);
    throw error;
  }

  await startPending({ phone: rep.rep_phone, kuid: "", email: made.email });
  redirect("/register/confirm");
}

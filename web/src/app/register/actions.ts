"use server";

import { redirect } from "next/navigation";

import { ApiError, register } from "@/lib/api";

/**
 * Registration, submitted as a plain form POST.
 *
 * **This must work with JavaScript switched off**, so the whole flow is a POST
 * followed by a redirect — the pattern the web had before JavaScript, and the
 * only one Opera Mini in proxy mode can be relied on to complete. Next.js
 * progressively enhances the same form when JavaScript is available, but
 * nothing here depends on that happening.
 *
 * On success it redirects to the card. On rejection it redirects back to the
 * form with the message, the field to point at, and the values already typed —
 * **except the password, which is never put in a URL.** A URL ends up in
 * browser history, in server logs and in the address bar of a shared phone at a
 * registration desk. Asking someone to retype eight characters is the cheaper
 * of the two costs by a wide margin.
 */
export async function registerAthlete(formData: FormData): Promise<void> {
  const text = (key: string): string => String(formData.get(key) ?? "").trim();

  const submitted = {
    full_name: text("full_name"),
    phone: text("phone"),
    date_of_birth: text("date_of_birth"),
    lga_id: text("lga_id"),
    sport: text("sport"),
    playing_position: text("playing_position") || null,
  };

  const bounceBack = (message: string, field?: string): never => {
    const params = new URLSearchParams({ error: message });
    if (field) params.set("field", field);
    // Everything except the password, so the person is not retyping their whole
    // life because one box was wrong.
    for (const [key, value] of Object.entries(submitted)) {
      if (value) params.set(key, value);
    }
    redirect(`/register?${params.toString()}`);
  };

  if (!formData.get("accept_privacy_notice")) {
    bounceBack(
      "Please accept the privacy notice so we can create your record.",
      "accept_privacy_notice",
    );
  }

  let result;
  try {
    result = await register({
      ...submitted,
      password: String(formData.get("password") ?? ""),
      accept_privacy_notice: true,
    });
  } catch (error) {
    if (error instanceof ApiError) bounceBack(error.message, error.field);
    throw error;
  }

  // Only a newly minted identity reaches here. A phone that is already
  // registered comes back as a field error above, never as somebody's card.
  redirect(`/card/${encodeURIComponent(result.kuid)}`);
}

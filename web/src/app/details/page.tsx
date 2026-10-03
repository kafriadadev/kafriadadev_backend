import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PageHead } from "@/components/PageHead";
import { Flash } from "@/components/Flash";
import { ApiError, getMyAthleteDetails } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { updateDetailsAction } from "./actions";

export const metadata: Metadata = { title: "Edit my details" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/**
 * Edit my details (ATH-02).
 *
 * Everything here is optional and none of it is in the KUID or the public
 * profile — sport and position, collected at registration, are shown for
 * context but are not editable on this screen.
 */
export default async function DetailsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let details;
  try {
    details = await getMyAthleteDetails(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    if (error instanceof ApiError && error.status === 404) {
      return (
        <div className="page stack">
          <h1>Edit my details</h1>
          <Flash variant="warn" title="No athlete record">
            <p className="mb0">This account is not registered as an athlete.</p>
          </Flash>
        </div>
      );
    }
    throw error;
  }

  const error = one(params.error);
  const badField = one(params.field);
  const saved = one(params.saved);
  const errClass = (field: string) => (badField === field ? "field field--error" : "field");

  return (
    <div className="page stack">
      <PageHead
        back={{ href: "/me", label: "My account" }}
        eyebrow="Account"
        title="Edit my details"
        lede={<>{details.sport} {details.playing_position ? ` · ${details.playing_position}` : ""} — set at registration. Everything below is optional.</>}
      />

      {saved ? (
        <Flash variant="good" title="Saved" autoDismissMs={4000}>
          <p className="mb0">Your details are updated.</p>
        </Flash>
      ) : null}

      {error ? (
        <Flash variant="bad" title="That did not work">
          <p className="mb0">{error}</p>
        </Flash>
      ) : null}

      <form action={updateDetailsAction} className="doc" noValidate>
        <div className="doc__body">
          <div className={errClass("gender")}>
            <label htmlFor="gender">Gender</label>
            <select id="gender" name="gender" defaultValue={details.gender ?? ""}>
              <option value="">Not stated</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="other">Other</option>
              <option value="prefer_not_to_say">Prefer not to say</option>
            </select>
            {badField === "gender" ? <span className="error">{error}</span> : null}
          </div>

          <div className={errClass("dominant_side")}>
            <label htmlFor="dominant_side">Dominant side</label>
            <select id="dominant_side" name="dominant_side" defaultValue={details.dominant_side ?? ""}>
              <option value="">Not stated</option>
              <option value="left">Left</option>
              <option value="right">Right</option>
              <option value="both">Both</option>
            </select>
            {badField === "dominant_side" ? <span className="error">{error}</span> : null}
          </div>

          <div className={errClass("secondary_sport")}>
            <label htmlFor="secondary_sport">Secondary sport</label>
            <span className="hint">Optional. Leave blank to clear it.</span>
            <input
              id="secondary_sport"
              name="secondary_sport"
              maxLength={40}
              defaultValue={details.secondary_sport ?? ""}
            />
            {badField === "secondary_sport" ? <span className="error">{error}</span> : null}
          </div>

          <div className={errClass("years_experience")}>
            <label htmlFor="years_experience">Years of experience</label>
            <input
              id="years_experience"
              name="years_experience"
              type="number"
              inputMode="numeric"
              min={0}
              max={100}
              defaultValue={details.years_experience ?? ""}
            />
            {badField === "years_experience" ? <span className="error">{error}</span> : null}
          </div>

          <button type="submit" className="btn btn--primary btn--block">Save</button>
        </div>
      </form>

    </div>
  );
}

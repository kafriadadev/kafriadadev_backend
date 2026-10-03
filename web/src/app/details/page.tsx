import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Flash } from "@/components/Flash";
import { PageHead } from "@/components/PageHead";
import { ApiError, getMyAthleteDetails } from "@/lib/api";
import { GENDERS, LEVELS, NOT_APPLICABLE, POSITIONS, SIDES, SPORTS } from "@/lib/profile";
import { sessionToken } from "@/lib/session";
import { updateDetailsAction } from "./actions";

export const metadata: Metadata = { title: "My details" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

const dob = (iso: string): string =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", {
    day: "numeric", month: "long", year: "numeric",
  });

/**
 * My details (ATH-02).
 *
 * The record in two parts. What registration fixed (name, sex, date of birth,
 * nationality, sport, LGA) is shown and not editable; changing it goes through a
 * coordinator, because it is what eligibility is judged on. What changes with
 * time (address, height, weight, positions, emergency contact) is edited here,
 * and all of it is required.
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
          <h1>My details</h1>
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
  const incomplete = !details.address_line || !details.height_cm || !details.emergency_name;
  const positions = [...(POSITIONS[details.sport] ?? []), NOT_APPLICABLE];

  const Field = ({
    name, label, hint, children,
  }: { name: string; label: string; hint?: string; children: React.ReactNode }) => (
    <div className={badField === name ? "field field--error" : "field"}>
      <label htmlFor={name}>{label}</label>
      {hint ? <span className="hint">{hint}</span> : null}
      {children}
      {badField === name ? <span className="error">{error}</span> : null}
    </div>
  );

  return (
    <div className="page stack">
      <PageHead
        back={{ href: "/me", label: "My account" }}
        eyebrow="Account"
        title="My details"
        lede="Keep these up to date. Coordinators and clubs rely on them."
      />

      {saved ? (
        <Flash variant="good" title="Saved" autoDismissMs={4000}>
          <p className="mb0">Your details are updated.</p>
        </Flash>
      ) : incomplete ? (
        <Flash variant="warn" title="Your record is incomplete">
          <p className="mb0">
            You registered before these details were asked for. Please fill in every field
            below and save.
          </p>
        </Flash>
      ) : null}

      {error ? (
        <Flash variant="bad" title="That did not work">
          <p className="mb0">{error}</p>
        </Flash>
      ) : null}

      <section className="doc" aria-label="Set at registration">
        <div className="doc__body">
          <p className="eyebrow">Set at registration</p>
          <dl className="facts">
            <div className="fact"><dt>Name</dt><dd>{details.full_name}</dd></div>
            <div className="fact">
              <dt>Sex</dt>
              <dd>{details.gender ? (GENDERS[details.gender] ?? details.gender) : "Not recorded"}</dd>
            </div>
            <div className="fact"><dt>Date of birth</dt><dd>{dob(details.date_of_birth)}</dd></div>
            <div className="fact">
              <dt>Nationality</dt>
              <dd>
                {details.nationality ?? "Not recorded"}
                {details.state_of_origin && details.state_of_origin !== NOT_APPLICABLE
                  ? ` · ${details.state_of_origin} State`
                  : ""}
              </dd>
            </div>
            <div className="fact"><dt>Sport</dt><dd>{details.sport}</dd></div>
            <div className="fact"><dt>LGA</dt><dd>{details.lga_name}</dd></div>
            {details.email ? (
              <div className="fact"><dt>Email</dt><dd className="break">{details.email}</dd></div>
            ) : null}
          </dl>
          <p className="hint mt-4 mb0">
            To correct any of these, speak to your LGA coordinator.
          </p>
        </div>
      </section>

      <form action={updateDetailsAction} className="doc" noValidate>
        <div className="doc__body">
          <fieldset className="fieldset">
            <legend>Sport profile</legend>
            <div className="field-row">
              <Field name="playing_position" label={`Main position or event (${details.sport})`}>
                <select id="playing_position" name="playing_position" required
                  defaultValue={details.playing_position ?? ""}>
                  <option value="">Choose</option>
                  {positions.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </Field>
              <Field name="secondary_position" label="Second position (optional)">
                <select id="secondary_position" name="secondary_position"
                  defaultValue={details.secondary_position ?? ""}>
                  <option value="">None</option>
                  {positions.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </Field>
            </div>
            <div className="field-row">
              <Field name="dominant_side" label="Stronger foot or hand">
                <select id="dominant_side" name="dominant_side" required
                  defaultValue={details.dominant_side ?? ""}>
                  <option value="">Choose</option>
                  {Object.entries(SIDES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </Field>
              <Field name="level_played" label="Highest level played">
                <select id="level_played" name="level_played" required
                  defaultValue={details.level_played ?? ""}>
                  <option value="">Choose</option>
                  {Object.entries(LEVELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </Field>
            </div>
            <div className="field-row">
              <Field name="height_cm" label="Height (cm)">
                <input id="height_cm" name="height_cm" type="number" inputMode="numeric"
                  min={120} max={230} required defaultValue={details.height_cm ?? ""} />
              </Field>
              <Field name="weight_kg" label="Weight (kg)">
                <input id="weight_kg" name="weight_kg" type="number" inputMode="numeric"
                  min={35} max={200} required defaultValue={details.weight_kg ?? ""} />
              </Field>
            </div>
            <div className="field-row">
              <Field name="years_experience" label="Years playing">
                <input id="years_experience" name="years_experience" type="number"
                  inputMode="numeric" min={0} max={60} required
                  defaultValue={details.years_experience ?? ""} />
              </Field>
              <Field name="secondary_sport" label="Another sport you play (optional)">
                <select id="secondary_sport" name="secondary_sport"
                  defaultValue={details.secondary_sport ?? ""}>
                  <option value="">None</option>
                  {SPORTS.filter((s) => s !== details.sport).map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </Field>
            </div>
          </fieldset>

          <fieldset className="fieldset">
            <legend>Address</legend>
            <Field name="address_line" label="Home address" hint="House number and street.">
              <input id="address_line" name="address_line" required autoComplete="street-address"
                defaultValue={details.address_line ?? ""} />
            </Field>
            <Field name="town" label="Town or city">
              <input id="town" name="town" required autoComplete="address-level2"
                defaultValue={details.town ?? ""} />
            </Field>
          </fieldset>

          <fieldset className="fieldset">
            <legend>Emergency contact</legend>
            <Field name="emergency_name" label="Full name">
              <input id="emergency_name" name="emergency_name" required
                defaultValue={details.emergency_name ?? ""} />
            </Field>
            <div className="field-row">
              <Field name="emergency_relationship" label="Relationship to you">
                <input id="emergency_relationship" name="emergency_relationship" required
                  defaultValue={details.emergency_relationship ?? ""} />
              </Field>
              <Field name="emergency_phone" label="Their phone number">
                <input id="emergency_phone" name="emergency_phone" type="tel" inputMode="tel"
                  required defaultValue={details.emergency_phone ?? ""} />
              </Field>
            </div>
          </fieldset>

          <button type="submit" className="btn btn--primary btn--block">Save my details</button>
        </div>
      </form>
    </div>
  );
}

import type { Metadata } from "next";

import { Flash } from "@/components/Flash";
import { PageHead } from "@/components/PageHead";
import { SubmitButton } from "@/components/SubmitButton";
import { listLgas } from "@/lib/api";
import {
  GENDERS, LEVELS, NATIONALITIES, NIGERIAN, NIGERIAN_STATES, NOT_APPLICABLE, PILOT_SPORT,
  POSITIONS, SIDES,
} from "@/lib/profile";
import { registerAthlete } from "./actions";

export const metadata: Metadata = { title: "Register as an athlete" };

// Always rendered fresh: which LGAs are open changes as waves roll out, and a
// cached page telling someone their town is closed when it just opened would be
// a bad way to lose a registration.
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/**
 * Registration (AUT-01). One plain form in five sections; no JavaScript needed.
 *
 * Every field the record needs is asked for here, once. Without a script the
 * position list cannot follow the chosen sport, so it is grouped by sport and the
 * API refuses a position from the wrong group.
 */
export default async function RegisterPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const params = await searchParams;
  const error = one(params.error);
  const badField = one(params.field);
  const value = (key: string) => one(params[key]);

  let lgas: Awaited<ReturnType<typeof listLgas>> = [];
  let loadFailed = false;
  try {
    lgas = await listLgas();
  } catch {
    loadFailed = true;
  }
  const open = lgas.filter((l) => l.is_open);
  const closed = lgas.filter((l) => !l.is_open);

  /** A labelled field, with its hint and, when it was the problem, the error. */
  const Field = ({
    name, label, hint, children,
  }: { name: string; label: string; hint?: string; children: React.ReactNode }) => (
    <div>
      <label htmlFor={name}>{label}</label>
      {hint ? <span id={`${name}-hint`}>{hint}</span> : null}
      {children}
      {badField === name ? <span>{error}</span> : null}
    </div>
  );

  const positionGroups = (
    <>
      {POSITIONS[PILOT_SPORT].map((p) => <option key={p} value={p}>{p}</option>)}
    </>
  );

  return (
    <div>
      <PageHead
        eyebrow="Athlete registration"
        title="Register as an athlete"
        lede="About five minutes. Have your phone, your email and an emergency contact's number ready. Every field is required unless it says optional."
      />

      {/* An error summary AND an error beside the field. The summary is what a
          screen reader announces on arrival; the inline message is what tells a
          sighted person which box to fix. Both, not either. */}
      {error ? (
        <Flash variant="bad" title="We could not register you yet">
          <p>{error}</p>
        </Flash>
      ) : null}

      {loadFailed ? (
        <Flash variant="bad" title="Cannot reach KAFRIADA NET">
          <p>
            We could not load the list of Local Government Areas. Please try again in a moment.
          </p>
        </Flash>
      ) : null}

      <form action={registerAthlete} noValidate>
        <div>
          <fieldset>
            <legend>1. About you</legend>
            <div>
              <Field name="first_name" label="First name" hint="As written on your ID document.">
                <input id="first_name" name="first_name" required autoComplete="given-name"
                  defaultValue={value("first_name")} aria-describedby="first_name-hint" />
              </Field>
              <Field name="surname" label="Surname">
                <input id="surname" name="surname" required autoComplete="family-name"
                  defaultValue={value("surname")} />
              </Field>
            </div>
            <Field name="middle_name" label="Middle name (optional)">
              <input id="middle_name" name="middle_name" autoComplete="additional-name"
                defaultValue={value("middle_name")} />
            </Field>
            <div>
              <Field name="gender" label="Sex" hint="The category you compete in.">
                <select id="gender" name="gender" required defaultValue={value("gender")}
                  aria-describedby="gender-hint">
                  <option value="">Choose</option>
                  {Object.entries(GENDERS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </Field>
              <Field name="date_of_birth" label="Date of birth" hint="18 or older during the pilot.">
                <input id="date_of_birth" name="date_of_birth" type="date" required
                  defaultValue={value("date_of_birth")} aria-describedby="date_of_birth-hint" />
              </Field>
            </div>
            <div>
              <Field name="nationality" label="Nationality">
                <select id="nationality" name="nationality" required
                  defaultValue={value("nationality") || NIGERIAN}>
                  {NATIONALITIES.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </Field>
              <Field name="state_of_origin" label="State of origin">
                <select id="state_of_origin" name="state_of_origin" required
                  defaultValue={value("state_of_origin")}>
                  <option value="">Choose your state</option>
                  {NIGERIAN_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
                  <option value={NOT_APPLICABLE}>Not Nigerian</option>
                </select>
              </Field>
            </div>
          </fieldset>

          <fieldset>
            <legend>2. Contact and address</legend>
            <div>
              <Field name="phone" label="Phone number" hint="One phone, one account.">
                <input id="phone" name="phone" type="tel" inputMode="tel" required
                  placeholder="0803 000 0000" autoComplete="tel"
                  defaultValue={value("phone")} aria-describedby="phone-hint" />
              </Field>
              <Field name="email" label="Email" hint="We send a code here to confirm it.">
                <input id="email" name="email" type="email" required autoComplete="email"
                  defaultValue={value("email")} aria-describedby="email-hint" />
              </Field>
            </div>
            <Field name="address_line" label="Home address" hint="House number and street.">
              <input id="address_line" name="address_line" required autoComplete="street-address"
                defaultValue={value("address_line")} aria-describedby="address_line-hint" />
            </Field>
            <div>
              <Field name="town" label="Town or city">
                <input id="town" name="town" required autoComplete="address-level2"
                  defaultValue={value("town")} />
              </Field>
              <Field name="lga_id" label="Local Government Area"
                hint="Where you live and register. It is printed into your ID and never changes.">
                <select id="lga_id" name="lga_id" required defaultValue={value("lga_id")}
                  aria-describedby="lga_id-hint">
                  <option value="">Choose your LGA</option>
                  {open.length > 0 ? (
                    <optgroup label="Open for registration">
                      {open.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                    </optgroup>
                  ) : null}
                  {/* Closed LGAs are listed rather than hidden, so somebody can find
                      their town and be told when it opens. */}
                  {closed.length > 0 ? (
                    <optgroup label="Opening soon, not yet accepting registrations">
                      {closed.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                    </optgroup>
                  ) : null}
                </select>
              </Field>
            </div>
          </fieldset>

          <fieldset>
            <legend>3. Your football</legend>
            <div>
              <input type="hidden" name="sport" value={PILOT_SPORT} />
              <Field name="level_played" label="Highest level played">
                <select id="level_played" name="level_played" required
                  defaultValue={value("level_played")}>
                  <option value="">Choose</option>
                  {Object.entries(LEVELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </Field>
            </div>
            <div>
              <Field name="playing_position" label="Main position">
                <select id="playing_position" name="playing_position" required
                  defaultValue={value("playing_position")}>
                  <option value="">Choose</option>
                  {positionGroups}
                </select>
              </Field>
              <Field name="secondary_position" label="Second position (optional)">
                <select id="secondary_position" name="secondary_position"
                  defaultValue={value("secondary_position")}>
                  <option value="">None</option>
                  {positionGroups}
                </select>
              </Field>
            </div>
            <div>
              <Field name="dominant_side" label="Stronger foot or hand">
                <select id="dominant_side" name="dominant_side" required
                  defaultValue={value("dominant_side")}>
                  <option value="">Choose</option>
                  {Object.entries(SIDES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </Field>
              <Field name="years_experience" label="Years playing">
                <input id="years_experience" name="years_experience" type="number" inputMode="numeric"
                  min={0} max={60} required defaultValue={value("years_experience")} />
              </Field>
            </div>
            <div>
              <Field name="height_cm" label="Height (cm)">
                <input id="height_cm" name="height_cm" type="number" inputMode="numeric"
                  min={120} max={230} required placeholder="175" defaultValue={value("height_cm")} />
              </Field>
              <Field name="weight_kg" label="Weight (kg)">
                <input id="weight_kg" name="weight_kg" type="number" inputMode="numeric"
                  min={35} max={200} required placeholder="70" defaultValue={value("weight_kg")} />
              </Field>
            </div>
          </fieldset>

          <fieldset>
            <legend>4. Emergency contact</legend>
            <Field name="emergency_name" label="Full name">
              <input id="emergency_name" name="emergency_name" required
                defaultValue={value("emergency_name")} />
            </Field>
            <div>
              <Field name="emergency_relationship" label="Relationship to you"
                hint="For example parent, brother, guardian.">
                <input id="emergency_relationship" name="emergency_relationship" required
                  defaultValue={value("emergency_relationship")}
                  aria-describedby="emergency_relationship-hint" />
              </Field>
              <Field name="emergency_phone" label="Their phone number">
                <input id="emergency_phone" name="emergency_phone" type="tel" inputMode="tel" required
                  defaultValue={value("emergency_phone")} />
              </Field>
            </div>
          </fieldset>

          <fieldset>
            <legend>5. Your account</legend>
            <Field name="password" label="Choose a password"
              hint="At least 10 characters. A short phrase you will remember works well.">
              <input id="password" name="password" type="password" required minLength={10}
                autoComplete="new-password" aria-describedby="password-hint" />
            </Field>
          </fieldset>

          <div>
            <input id="accept_privacy_notice" name="accept_privacy_notice" type="checkbox"
              value="yes" required />
            <label htmlFor="accept_privacy_notice">
              I am 18 or older, the details above are true, and I accept the{" "}
              <a href="/privacy">privacy notice</a>. I understand that if I later ask to be
              deleted, my personal details are erased but my KAFRIADA NET ID and payment records
              are kept.
            </label>
          </div>

          <div>
            <SubmitButton pending="Creating your account…">Register</SubmitButton>
          </div>

          <p>
            Already registered? <a href="/sign-in">Sign in</a>
          </p>
        </div>
      </form>
    </div>
  );
}

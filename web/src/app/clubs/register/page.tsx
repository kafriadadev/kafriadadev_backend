import type { Metadata } from "next";

import { ClubFields } from "@/components/ClubFields";
import { Flash } from "@/components/Flash";
import { PageHead } from "@/components/PageHead";
import { SubmitButton } from "@/components/SubmitButton";
import { listLgas } from "@/lib/api";
import { OFFICIAL_ROLES } from "@/lib/clubProfile";
import { signUpClubAction } from "./actions";

export const metadata: Metadata = { title: "Register a club" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;

/**
 * A club signs up (CLB-01). Public: the club's representative creates their account
 * and the club in one form. Once they confirm their email, the club goes to a
 * KAFRIADA administrator for approval.
 */
export default async function ClubSignUpPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const get = (k: string): string => {
    const v = params[k];
    return Array.isArray(v) ? (v[0] ?? "") : (v ?? "");
  };
  const all = (k: string): string[] => {
    const v = params[k];
    return Array.isArray(v) ? v : v ? [v] : [];
  };
  const error = get("error");
  const badField = get("field");
  const duplicate = get("duplicate") === "1";

  let open: { id: string; name: string }[] = [];
  let loadFailed = false;
  try {
    open = (await listLgas()).filter((l) => l.is_open);
  } catch {
    loadFailed = true;
  }

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
        eyebrow="Clubs"
        title="Register a club"
        lede="For a club's chairman, secretary, manager or coach. About ten minutes. Every field is required unless it says optional."
      />

      <div className="notice">
        <p className="notice__title">How it works</p>
        <ol className="bullets mb0">
          <li>Fill in the club&rsquo;s details and your own.</li>
          <li>Confirm your email with the code we send.</li>
          <li>A KAFRIADA administrator reviews the club. Once approved, you can add players.</li>
        </ol>
      </div>

      {error ? (
        <Flash
          variant={duplicate ? "warn" : "bad"}
          title={duplicate ? "This name is already used" : "We could not register the club yet"}
        >
          <p className="mb0">
            {error}
            {duplicate ? " If yours is a different club, tick the box below and submit again." : ""}
          </p>
        </Flash>
      ) : null}
      {loadFailed ? (
        <Flash variant="bad" title="Cannot reach KAFRIADA">
          <p className="mb0">We could not load the list of areas. Please try again in a moment.</p>
        </Flash>
      ) : null}

      <form action={signUpClubAction} className="doc" noValidate>
        <div className="doc__body">
          <ClubFields values={{ get, all }} badField={badField} error={error} lgas={open} />

          <fieldset className="fieldset">
            <legend>You, the club&rsquo;s representative</legend>
            <p className="hint mb-3">
              This becomes the club&rsquo;s account. Use your own phone and email, not the
              club&rsquo;s.
            </p>
            <div className="field-row">
              <Field name="rep_first_name" label="First name">
                <input id="rep_first_name" name="rep_first_name" required autoComplete="given-name"
                  defaultValue={get("rep_first_name")} />
              </Field>
              <Field name="rep_surname" label="Surname">
                <input id="rep_surname" name="rep_surname" required autoComplete="family-name"
                  defaultValue={get("rep_surname")} />
              </Field>
            </div>
            <Field name="rep_role" label="Your role in the club">
              <select id="rep_role" name="rep_role" required defaultValue={get("rep_role")}>
                <option value="">Choose</option>
                {OFFICIAL_ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </Field>
            <div className="field-row">
              <Field name="rep_phone" label="Your phone">
                <input id="rep_phone" name="rep_phone" type="tel" inputMode="tel" required
                  autoComplete="tel" defaultValue={get("rep_phone")} />
              </Field>
              <Field name="rep_email" label="Your email" hint="We send a code here to confirm it.">
                <input id="rep_email" name="rep_email" type="email" required autoComplete="email"
                  defaultValue={get("rep_email")} />
              </Field>
            </div>
            <Field name="password" label="Choose a password" hint="At least 10 characters.">
              <input id="password" name="password" type="password" required minLength={10}
                autoComplete="new-password" />
            </Field>
          </fieldset>

          {duplicate ? (
            <div className="field">
              <label htmlFor="confirm_duplicate" className="cluster">
                <input id="confirm_duplicate" name="confirm_duplicate" type="checkbox" />
                This is a different club with the same name
              </label>
            </div>
          ) : null}

          <div className={badField === "accept_privacy_notice" ? "consent field--error" : "consent"}>
            <input id="accept_privacy_notice" name="accept_privacy_notice" type="checkbox"
              value="yes" required />
            <label htmlFor="accept_privacy_notice">
              I represent this club, the details above are true, and I accept the{" "}
              <a href="/privacy">privacy notice</a>.
            </label>
          </div>

          <div className="mt-5">
            <SubmitButton pending="Registering the club…">Register the club</SubmitButton>
          </div>
          <p className="hint form-foot">
            Already registered? <a href="/sign-in">Sign in</a>
          </p>
        </div>
      </form>
    </div>
  );
}

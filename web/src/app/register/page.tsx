import type { Metadata } from "next";

import { listLgas } from "@/lib/api";
import { registerAthlete } from "./actions";

export const metadata: Metadata = { title: "Register free" };

// Always rendered fresh: which LGAs are open changes as waves roll out, and a
// cached page telling someone their town is closed when it just opened would be
// a bad way to lose a registration.
export const dynamic = "force-dynamic";

const SPORTS = [
  "Football", "Athletics", "Basketball", "Volleyball", "Handball",
  "Boxing", "Wrestling", "Table Tennis", "Badminton", "Swimming",
] as const;

const POSITIONS = [
  "Goalkeeper", "Defender", "Midfielder", "Striker", "Winger", "Not applicable",
] as const;

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/** Registration (AUT-01). A plain form. No JavaScript required to complete it. */
export default async function RegisterPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const params = await searchParams;
  const error = one(params.error);
  const badField = one(params.field);

  let lgas: Awaited<ReturnType<typeof listLgas>> = [];
  let loadFailed = false;
  try {
    lgas = await listLgas();
  } catch {
    loadFailed = true;
  }

  const open = lgas.filter((l) => l.is_open);
  const closed = lgas.filter((l) => !l.is_open);
  const errClass = (field: string) =>
    badField === field ? "field field--error" : "field";

  return (
    <div className="stack">
      <p className="eyebrow">Step 1 of 3 · Free</p>
      <h1>Get your KAFRIADA ID</h1>
      <p className="lede">
        About two minutes. You need a phone that can receive SMS.
      </p>

      {/* An error summary AND an error beside the field. The summary is what a
          screen reader announces on arrival; the inline message is what tells a
          sighted person which box to fix. Both, not either. */}
      {error ? (
        <div className="notice notice--bad" role="alert" tabIndex={-1}>
          <p className="notice__title">We could not register you yet</p>
          <p style={{ marginBottom: 0 }}>{error}</p>
        </div>
      ) : null}

      {loadFailed ? (
        <div className="notice notice--bad" role="alert">
          <p className="notice__title">Cannot reach KAFRIADA</p>
          <p style={{ marginBottom: 0 }}>
            We could not load the list of Local Government Areas. Please try
            again in a moment.
          </p>
        </div>
      ) : null}

      <form action={registerAthlete} className="doc" noValidate>
        <div className="doc__body">
          <div className={errClass("full_name")}>
            <label htmlFor="full_name">Full name</label>
            <span className="hint" id="name-hint">
              As written on your ID document.
            </span>
            <input
              id="full_name"
              name="full_name"
              required
              autoComplete="name"
              defaultValue={one(params.full_name)}
              aria-describedby="name-hint"
            />
            {badField === "full_name" ? (
              <span className="error">{error}</span>
            ) : null}
          </div>

          <div className={errClass("phone")}>
            <label htmlFor="phone">Phone number</label>
            <span className="hint" id="phone-hint">
              We send a code to this number. One phone, one KAFRIADA ID.
            </span>
            <input
              id="phone"
              name="phone"
              type="tel"
              inputMode="tel"
              required
              placeholder="0803 000 0000"
              autoComplete="tel"
              defaultValue={one(params.phone)}
              aria-describedby="phone-hint"
            />
            {badField === "phone" ? <span className="error">{error}</span> : null}
          </div>

          <div className={errClass("date_of_birth")}>
            <label htmlFor="date_of_birth">Date of birth</label>
            <span className="hint" id="dob-hint">
              You must be 18 or older during the pilot.
            </span>
            {/* A native date input. A custom picker would need JavaScript and
                would fail on exactly the phones this has to work on. */}
            <input
              id="date_of_birth"
              name="date_of_birth"
              type="date"
              required
              defaultValue={one(params.date_of_birth)}
              aria-describedby="dob-hint"
            />
            {badField === "date_of_birth" ? (
              <span className="error">{error}</span>
            ) : null}
          </div>

          <div className={errClass("lga_id")}>
            <label htmlFor="lga_id">Local Government Area</label>
            <span className="hint" id="lga-hint">
              Where you are registering. This is printed in your ID and never
              changes, even if you move.
            </span>
            <select
              id="lga_id"
              name="lga_id"
              required
              defaultValue={one(params.lga_id)}
              aria-describedby="lga-hint"
            >
              <option value="">Choose your LGA</option>
              {open.length > 0 ? (
                <optgroup label="Open for registration">
                  {open.map((l) => (
                    <option key={l.id} value={l.id}>{l.name}</option>
                  ))}
                </optgroup>
              ) : null}
              {/* Closed LGAs are listed rather than hidden, so somebody can find
                  their town and be told when it opens — instead of concluding
                  the whole thing is broken. */}
              {closed.length > 0 ? (
                <optgroup label="Opening soon — not yet accepting registrations">
                  {closed.map((l) => (
                    <option key={l.id} value={l.id}>{l.name}</option>
                  ))}
                </optgroup>
              ) : null}
            </select>
            {badField === "lga_id" ? <span className="error">{error}</span> : null}
          </div>

          <div className={errClass("sport")}>
            <label htmlFor="sport">Sport</label>
            <select
              id="sport"
              name="sport"
              required
              defaultValue={one(params.sport) || "Football"}
            >
              {SPORTS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          <div className="field">
            <label htmlFor="playing_position">Position</label>
            <span className="hint">Optional.</span>
            <select
              id="playing_position"
              name="playing_position"
              defaultValue={one(params.playing_position)}
            >
              <option value="">Not stated</option>
              {POSITIONS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>

          <div className={errClass("password")}>
            <label htmlFor="password">Choose a password</label>
            <span className="hint" id="pw-hint">
              At least 10 characters. A short phrase you will remember is better
              than a short word with symbols in it.
            </span>
            <input
              id="password"
              name="password"
              type="password"
              required
              minLength={10}
              autoComplete="new-password"
              aria-describedby="pw-hint"
            />
            {badField === "password" ? (
              <span className="error">{error}</span>
            ) : null}
          </div>

          <div className="consent">
            <input
              id="accept_privacy_notice"
              name="accept_privacy_notice"
              type="checkbox"
              value="yes"
              required
            />
            <label htmlFor="accept_privacy_notice">
              I am 18 or older and I accept the{" "}
              <a href="/privacy">privacy notice</a>. I understand that if I later
              ask to be deleted, my name, photograph and phone number are erased
              but my KAFRIADA ID and payment records are kept.
            </label>
          </div>

          <button type="submit" className="btn btn--primary btn--block"
                  style={{ marginTop: "var(--s5)" }}>
            Create my KAFRIADA ID
          </button>

          <p className="hint" style={{ textAlign: "center", marginTop: "var(--s4)" }}>
            Already registered? <a href="/sign-in">Sign in</a> or{" "}
            <a href="/find">look up your ID</a>
          </p>
        </div>
      </form>
    </div>
  );
}

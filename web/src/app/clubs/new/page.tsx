import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { SubmitButton } from "@/components/SubmitButton";
import { Flash } from "@/components/Flash";
import { listLgas } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { registerClubAction } from "./actions";

export const metadata: Metadata = { title: "Register a club" };
export const dynamic = "force-dynamic";

const SPORTS = [
  "Football", "Athletics", "Basketball", "Volleyball", "Handball",
  "Boxing", "Wrestling", "Table Tennis", "Badminton", "Swimming",
] as const;

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/** Register a club (CLB-01). A plain form; the API decides everything. */
export default async function NewClubPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  if (!(await sessionToken())) redirect("/sign-in");

  let open: Awaited<ReturnType<typeof listLgas>> = [];
  let loadFailed = false;
  try {
    open = (await listLgas()).filter((l) => l.is_open);
  } catch {
    loadFailed = true;
  }

  const error = one(params.error);
  const badField = one(params.field);
  const duplicate = one(params.duplicate) === "1";
  const errClass = (field: string) => (badField === field ? "field field--error" : "field");

  return (
    <div className="stack">
      <p className="eyebrow">Clubs</p>
      <h1>Register a club</h1>
      <p className="lede">
        Registering is free. You become the club&rsquo;s administrator. A verified club badge is
        optional and costs ₦15,000.
      </p>

      {error ? (
        <Flash variant={duplicate ? "warn" : "bad"} title={duplicate ? "This name is already used" : "We could not register the club"}>
          <p style={{ marginBottom: 0 }}>
            {error}
            {duplicate ? " If yours is a different club, tick the box below and register it again." : ""}
          </p>
        </Flash>
      ) : null}

      {loadFailed ? (
        <Flash variant="bad" title="Cannot reach KAFRIADA">
          <p style={{ marginBottom: 0 }}>We could not load the list of areas. Please try again in a moment.</p>
        </Flash>
      ) : null}

      <form action={registerClubAction} className="doc" noValidate>
        <div className="doc__body">
          <div className={errClass("name")}>
            <label htmlFor="name">Club name</label>
            <input id="name" name="name" required defaultValue={one(params.name)} />
            {badField === "name" && !duplicate ? <span className="error">{error}</span> : null}
          </div>

          <div className={errClass("year_founded")}>
            <label htmlFor="year_founded">Year founded</label>
            <input
              id="year_founded"
              name="year_founded"
              inputMode="numeric"
              placeholder="2015"
              defaultValue={one(params.year_founded)}
            />
            {badField === "year_founded" ? <span className="error">{error}</span> : null}
          </div>

          <div className={errClass("lga_id")}>
            <label htmlFor="lga_id">Local government area</label>
            <select id="lga_id" name="lga_id" required defaultValue={one(params.lga_id)}>
              <option value="">Choose an area</option>
              {open.map((l) => (
                <option key={l.id} value={l.id}>{l.name}</option>
              ))}
            </select>
            {badField === "lga_id" ? <span className="error">{error}</span> : null}
          </div>

          <div className={errClass("sport")}>
            <label htmlFor="sport">Sport</label>
            <select id="sport" name="sport" required defaultValue={one(params.sport)}>
              <option value="">Choose a sport</option>
              {SPORTS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            {badField === "sport" ? <span className="error">{error}</span> : null}
          </div>

          <div className={errClass("contact_phone")}>
            <label htmlFor="contact_phone">Contact phone</label>
            <input
              id="contact_phone"
              name="contact_phone"
              type="tel"
              inputMode="tel"
              required
              placeholder="0803 000 0000"
              autoComplete="tel"
              defaultValue={one(params.contact_phone)}
            />
            {badField === "contact_phone" ? <span className="error">{error}</span> : null}
          </div>

          {duplicate ? (
            <div className="field">
              <label htmlFor="confirm_duplicate" style={{ display: "flex", gap: "var(--s3)", alignItems: "center" }}>
                <input id="confirm_duplicate" name="confirm_duplicate" type="checkbox" />
                This is a different club with the same name
              </label>
            </div>
          ) : null}

          <SubmitButton pending="Registering your club…">Register club</SubmitButton>
        </div>
      </form>
    </div>
  );
}

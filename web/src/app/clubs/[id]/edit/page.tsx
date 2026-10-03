import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PageHead } from "@/components/PageHead";
import { NoAccess } from "@/components/NoAccess";
import { Flash } from "@/components/Flash";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError, type ClubDashboard, getClub } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { updateClubAction } from "./actions";

export const metadata: Metadata = { title: "Edit club details" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/** Edit a club's name, contact number and founding year. Sport and area stay as registered. */
export default async function EditClubPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Search>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let club: ClubDashboard;
  try {
    club = await getClub(token, id);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403 || error.status === 404) {
        return (
          <NoAccess title="Edit club details" message="You can only edit a club you administer." />
        );
      }
    }
    throw error;
  }

  const error = one(query.error);
  const badField = one(query.field);
  const errClass = (field: string) => (badField === field ? "field field--error" : "field");
  const value = (key: string, fallback: string) => (one(query[key]) !== "" ? one(query[key]) : fallback);

  return (
    <div className="page stack">
      <PageHead
        eyebrow={<>Club &middot; {club.name}</>}
        title="Edit club details"
      />

      {error ? (
        <Flash variant="bad" title="We could not save that">
          <p className="mb0">{error}</p>
        </Flash>
      ) : null}

      <form action={updateClubAction} className="doc" noValidate>
        <div className="doc__body">
          <input type="hidden" name="club" value={id} />
          <div className={errClass("name")}>
            <label htmlFor="name">Club name</label>
            <input id="name" name="name" required defaultValue={value("name", club.name)} />
            {badField === "name" ? <span className="error">{error}</span> : null}
          </div>
          <div className={errClass("year_founded")}>
            <label htmlFor="year_founded">Year founded</label>
            <input
              id="year_founded"
              name="year_founded"
              inputMode="numeric"
              defaultValue={value("year_founded", club.year_founded ? String(club.year_founded) : "")}
            />
            {badField === "year_founded" ? <span className="error">{error}</span> : null}
          </div>
          <div className={errClass("contact_phone")}>
            <label htmlFor="contact_phone">Contact phone</label>
            <input
              id="contact_phone"
              name="contact_phone"
              type="tel"
              inputMode="tel"
              required
              defaultValue={value("contact_phone", club.contact_phone)}
            />
            {badField === "contact_phone" ? <span className="error">{error}</span> : null}
          </div>
          <p className="hint">
            {club.sport} &middot; {club.lga_name}. The sport and area a club is registered under
            do not change.
          </p>
          <SubmitButton pending="Saving…">Save</SubmitButton>
        </div>
      </form>

      <p><a href={`/clubs/${encodeURIComponent(id)}?tab=details`}>Cancel</a></p>
    </div>
  );
}

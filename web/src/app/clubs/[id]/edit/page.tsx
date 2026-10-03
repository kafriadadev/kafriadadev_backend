import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ClubFields } from "@/components/ClubFields";
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

/** Edit a club's record. Sport and area stay as registered. */
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
  // After a refusal the typed values come back in the address; otherwise the record.
  const edited = one(query.edited) === "1";
  const stored = (club.profile ?? {}) as Record<string, unknown>;
  const recordValue = (k: string): string => {
    if (k === "name") return club.name;
    if (k === "contact_phone") return club.contact_phone;
    if (k === "year_founded") return club.year_founded ? String(club.year_founded) : "";
    const v = stored[k];
    return v === null || v === undefined ? "" : String(v);
  };
  const get = (k: string): string => (edited ? one(query[k]) : recordValue(k));
  const all = (k: string): string[] => {
    if (!edited) return Array.isArray(stored[k]) ? (stored[k] as string[]) : [];
    const v = query[k];
    return Array.isArray(v) ? v : v ? [v] : [];
  };

  return (
    <div className="page stack">
      <PageHead
        back={{ href: `/clubs/${encodeURIComponent(id)}?tab=details`, label: club.name }}
        eyebrow="Club"
        title="Edit club details"
        lede="Every field is required unless it says optional. Sport and area stay as registered."
      />

      {error ? (
        <Flash variant="bad" title="We could not save that">
          <p className="mb0">{error}</p>
        </Flash>
      ) : null}

      <form action={updateClubAction} className="doc" noValidate>
        <div className="doc__body">
          <input type="hidden" name="club" value={id} />
          <ClubFields
            values={{ get, all }}
            badField={badField}
            error={error}
            fixed={{ sport: club.sport, lga_name: club.lga_name }}
          />
          <SubmitButton pending="Saving…">Save club details</SubmitButton>
        </div>
      </form>
    </div>
  );
}

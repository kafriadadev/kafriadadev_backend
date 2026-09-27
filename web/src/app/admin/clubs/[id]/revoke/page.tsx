import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AdminNav } from "@/components/AdminNav";
import { Flash } from "@/components/Flash";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError, type ClubDashboard, getClub } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { revokeClubAction } from "./actions";

export const metadata: Metadata = { title: "Withdraw a club's verification" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/**
 * Withdraw a club's verified badge — the club equivalent of ADM-03.
 *
 * A super administrator only, and it asks for their password again, the same as any
 * other admin action that undoes a decision. The badge comes down immediately; the
 * club itself is not otherwise affected, and it can be verified again from scratch.
 */
export default async function RevokeClubPage({
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
          <div className="stack">
            <AdminNav current="/admin/clubs" />
            <h1>Withdraw a club&rsquo;s verification</h1>
            <Flash variant="bad" title="Not found or not allowed">
              <p style={{ marginBottom: 0 }}>
                There is no such club, or you do not have access. <a href="/admin/clubs">Back to clubs</a>
              </p>
            </Flash>
          </div>
        );
      }
    }
    throw error;
  }

  const error = one(query.error);

  return (
    <div className="stack">
      <AdminNav current="/admin/clubs" />
      <p className="eyebrow">Clubs</p>
      <h1>Withdraw a club&rsquo;s verification</h1>

      {error ? (
        <Flash variant="bad" title="That did not work">
          <p style={{ marginBottom: 0 }}>{error}</p>
        </Flash>
      ) : null}

      <section className="doc" aria-label={club.name}>
        <div className="doc__body">
          <dl className="facts">
            <div className="fact"><dt>Club</dt><dd>{club.name}</dd></div>
            <div className="fact"><dt>Area</dt><dd>{club.lga_name}</dd></div>
            <div className="fact">
              <dt>Verification</dt>
              <dd>{club.verified ? "Verified" : "Not currently verified"}</dd>
            </div>
          </dl>

          {club.verified ? (
            <form action={revokeClubAction} style={{ marginTop: "var(--s5)" }}>
              <input type="hidden" name="club" value={id} />
              <div className="field">
                <label htmlFor="reason">Reason</label>
                <span className="hint">Kept permanently. Shown to the club, unlike a routine note.</span>
                <textarea id="reason" name="reason" maxLength={2000} required />
              </div>
              <div className="field">
                <label htmlFor="current_password">Your password</label>
                <span className="hint">Confirms this is really you, same as any other admin action.</span>
                <input
                  id="current_password"
                  name="current_password"
                  type="password"
                  autoComplete="current-password"
                  required
                />
              </div>
              <SubmitButton pending="Withdrawing…">Withdraw this club&rsquo;s verification</SubmitButton>
            </form>
          ) : (
            <p className="hint" style={{ marginTop: "var(--s4)", marginBottom: 0 }}>
              Nothing to withdraw — only a currently verified club can be.
            </p>
          )}
        </div>
      </section>

      <p><a href="/admin/clubs">Back to clubs</a></p>
    </div>
  );
}

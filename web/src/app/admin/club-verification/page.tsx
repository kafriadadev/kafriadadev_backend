import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AdminNav } from "@/components/AdminNav";
import { Flash } from "@/components/Flash";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError, type ClubVerificationWaiting, getClubVerificationQueue } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { decideAction } from "./actions";

export const metadata: Metadata = { title: "Club reviews" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

const stamp = (iso: string): string =>
  new Date(iso).toLocaleString("en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lagos",
  });

/**
 * Club reviews: the registration document or LGA letter of each club that has paid, and a
 * decision. A rejection needs a reason, which the club reads exactly as written.
 */
export default async function ClubReviewsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let waiting: ClubVerificationWaiting[];
  try {
    waiting = await getClubVerificationQueue(token);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403) {
        return (
          <div className="stack">
            <h1>Club reviews</h1>
            <Flash variant="bad" title="You do not have access to this">
              <p style={{ marginBottom: 0 }}>Only a super administrator can open this.</p>
            </Flash>
          </div>
        );
      }
    }
    throw error;
  }

  const done = one(params.done);
  const error = one(params.error);

  return (
    <div className="stack">
      <AdminNav current="/admin/club-verification" />
      <h1>Club reviews</h1>

      {done ? (
        <Flash variant="good" title={done === "approved" ? "Club verified" : "Rejected"}>
          <p style={{ marginBottom: 0 }}>The club has been told.</p>
        </Flash>
      ) : null}
      {error ? (
        <Flash variant="bad" title="That did not work">
          <p style={{ marginBottom: 0 }}>{error}</p>
        </Flash>
      ) : null}

      {waiting.length === 0 ? <p className="hint">No club is waiting for a decision.</p> : null}

      {waiting.map((w) => (
        <section className="doc" key={w.club_id} aria-label={w.club_name}>
          <div className="doc__body">
            <p style={{ fontWeight: 700, marginBottom: "var(--s2)" }}>{w.club_name}</p>
            <p className="hint">{w.lga_name} &middot; submitted {stamp(w.submitted_at)}</p>
            <figure className="evidence">
              <figcaption>Registration document or LGA letter</figcaption>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`/admin/club-verification/${w.club_id}/document`}
                alt="The document the club submitted"
                width={320}
                loading="lazy"
              />
            </figure>

            <form action={decideAction}>
              <input type="hidden" name="club" value={w.club_id} />
              <input type="hidden" name="decision" value="approve" />
              <SubmitButton className="btn btn--primary btn--block" pending="Verifying…">
                Approve
              </SubmitButton>
            </form>

            <form action={decideAction} style={{ marginTop: "var(--s4)" }}>
              <input type="hidden" name="club" value={w.club_id} />
              <input type="hidden" name="decision" value="reject" />
              <div className="field">
                <label htmlFor={`reason-${w.club_id}`}>Reject with a reason</label>
                <span className="hint">The club reads this exactly as you write it.</span>
                <textarea id={`reason-${w.club_id}`} name="reason" maxLength={1000} required />
              </div>
              <SubmitButton className="btn btn--ghost btn--block" pending="Rejecting…">
                Reject with reason
              </SubmitButton>
            </form>
          </div>
        </section>
      ))}
    </div>
  );
}

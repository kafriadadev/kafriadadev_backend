import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { NoAccess } from "@/components/NoAccess";
import { AdminShell } from "@/components/AdminNav";
import { EmptyState } from "@/components/EmptyState";
import { PageHead } from "@/components/PageHead";
import { Flash } from "@/components/Flash";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError, type ClubVerificationWaiting, getClubVerificationQueue } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { decideAction } from "./actions";
import { Badge, Card } from "@/components/console";

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
          <NoAccess title="Club reviews" />
        );
      }
    }
    throw error;
  }

  const done = one(params.done);
  const error = one(params.error);

  return (
    <AdminShell current="/admin/club-verification">
      <PageHead title="Club reviews" lede="Clubs that have paid for verification and are waiting for a decision." />

      {done ? (
        <Flash variant="good" title={done === "approved" ? "Club verified" : "Rejected"}>
          <p>The club has been told.</p>
        </Flash>
      ) : null}
      {error ? (
        <Flash variant="bad" title="That did not work">
          <p>{error}</p>
        </Flash>
      ) : null}

      {waiting.length === 0 ? <EmptyState title="No club is waiting for a decision" /> : null}

      {waiting.map((w) => (
        <Card key={w.club_id} title={w.club_name} description={`${w.lga_name} · submitted ${stamp(w.submitted_at)}`} actions={<Badge tone="warn">Waiting for a decision</Badge>}>
          <div className="grid gap-6 md:grid-cols-[18rem_1fr]">
            <figure className="m-0">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`/admin/club-verification/${w.club_id}/document`}
                alt="The document the club submitted"
                width={320}
                loading="lazy"
                className="w-full rounded-[var(--radius-control)] border border-line bg-surface object-contain"
              />
              <figcaption className="mt-2 text-xs text-muted">Registration document or LGA letter</figcaption>
            </figure>
            <div className="space-y-5">
              <form action={decideAction}>
                <input type="hidden" name="club" value={w.club_id} />
                <input type="hidden" name="decision" value="approve" />
                <p className="text-sm text-muted">Approve if the document names this club and its LGA.</p>
                <SubmitButton pending="Verifying…">Approve and verify</SubmitButton>
              </form>
              <form action={decideAction} className="border-t border-line pt-5">
                <input type="hidden" name="club" value={w.club_id} />
                <input type="hidden" name="decision" value="reject" />
                <div>
                  <label htmlFor={`reason-${w.club_id}`}>Or reject, with a reason</label>
                  <span>The club reads this exactly as you write it.</span>
                  <textarea id={`reason-${w.club_id}`} name="reason" maxLength={1000} required />
                </div>
                <SubmitButton variant="quietDanger" pending="Rejecting…">Reject</SubmitButton>
              </form>
            </div>
          </div>
        </Card>
      ))}
    </AdminShell>
  );
}

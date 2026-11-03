import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AdminShell } from "@/components/AdminNav";
import { Badge, Card } from "@/components/console";
import { EmptyState } from "@/components/EmptyState";
import { Flash } from "@/components/Flash";
import { NoAccess } from "@/components/NoAccess";
import { PageHead } from "@/components/PageHead";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError, type ClubStage3, getClubStage3Queue, getClubStage3Review } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { decideStage3Action } from "./actions";

export const metadata: Metadata = { title: "Stage three reviews" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));
const stamp = (iso: string): string =>
  new Date(iso).toLocaleString("en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lagos",
  });

/**
 * Stage three reviews: the links and photos of each club that has paid, and a decision.
 * A rejection needs a reason, which the club reads exactly as written.
 */
export default async function ClubStage3ReviewsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let waiting: { club_id: string; club_name: string; lga_name: string; submitted_at: string; detail: ClubStage3 }[];
  try {
    const queue = await getClubStage3Queue(token);
    waiting = await Promise.all(
      queue.map(async (w) => ({ ...w, detail: await getClubStage3Review(token, w.club_id) })),
    );
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403) return <NoAccess title="Stage three reviews" />;
    }
    throw error;
  }

  const done = one(params.done);
  const error = one(params.error);

  return (
    <AdminShell current="/admin/club-stage-three">
      <PageHead title="Stage three reviews" lede="Verified clubs that have paid for stage three and are waiting for a decision." />

      {done ? (
        <Flash variant="good" title={done === "approved" ? "Club moved to stage three" : "Rejected"}>
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
          <div className="space-y-6">
            <div>
              <h3 className="text-sm font-bold">Links</h3>
              <ul className="mt-2 space-y-1">
                {w.detail.links.map((link) => (
                  <li key={link}><a href={link} rel="noopener noreferrer nofollow" target="_blank">{link}</a></li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="text-sm font-bold">Photos</h3>
              <ul className="mt-2 grid grid-cols-2 gap-3 md:grid-cols-3">
                {w.detail.photos.filter((p) => p.status === "ready").map((p) => (
                  <li key={p.media_id}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={`/admin/club-stage-three/${w.club_id}/photo/${p.media_id}`}
                      alt={`A photo submitted by ${w.club_name}`}
                      loading="lazy"
                      className="aspect-[4/3] w-full rounded-[var(--radius-control)] border border-line bg-surface object-cover"
                    />
                  </li>
                ))}
              </ul>
            </div>
            <form action={decideStage3Action}>
              <input type="hidden" name="club" value={w.club_id} />
              <input type="hidden" name="decision" value="approve" />
              <p className="text-sm text-muted">Approve if the links and photos are this club&apos;s own.</p>
              <SubmitButton pending="Approving…">Approve stage three</SubmitButton>
            </form>
            <form action={decideStage3Action} className="border-t border-line pt-5">
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
        </Card>
      ))}
    </AdminShell>
  );
}

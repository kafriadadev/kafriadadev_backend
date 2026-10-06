import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { NoAccess } from "@/components/NoAccess";
import { AdminShell } from "@/components/AdminNav";
import { PageHead } from "@/components/PageHead";
import { Flash } from "@/components/Flash";
import { Stat } from "@/components/Stat";
import { type AdminOverview, ApiError, getAdminOverview } from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";

export const metadata: Metadata = { title: "Administrator" };
export const dynamic = "force-dynamic";

const REVIEW_TARGET_HOURS = 24;

const stamp = (iso: string): string =>
  new Date(iso).toLocaleString("en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lagos",
  });

/**
 * The administrator's home (ADM-01): money in the last day, the funnel, and the way into
 * everything else. A failed ledger check takes over the top of the screen — nothing else
 * matters until it is resolved. Deeper analysis is not built here.
 */
export default async function AdminHome() {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let o: AdminOverview;
  try {
    o = await getAdminOverview(token);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403) {
        return (
          <NoAccess title="Administrator" />
        );
      }
    }
    throw error;
  }

  return (
    <AdminShell current="/admin">
      <PageHead eyebrow="Administrator" title="Overview" app />

      {o.ledger_ok === false ? (
        <Flash variant="bad" title="The ledger check failed">
          <p>
            The last nightly check found a problem
            {o.ledger_checked_at ? ` (${stamp(o.ledger_checked_at)})` : ""}. Nothing else matters
            until it is resolved.
          </p>
        </Flash>
      ) : null}
      {o.unresolved > 0 ? (
        <Flash variant="warn" title={`${o.unresolved} unresolved ${o.unresolved === 1 ? "payment" : "payments"}`}>
          <p>
            These need a person: the amount paid did not match what was agreed.
          </p>
        </Flash>
      ) : null}
      {o.review_median_hours !== null && o.review_median_hours > REVIEW_TARGET_HOURS ? (
        <Flash variant="warn" title="Reviews are slower than the target">
          <p>
            The median decision took {o.review_median_hours} hours this month; the target is{" "}
            {REVIEW_TARGET_HOURS}.
          </p>
        </Flash>
      ) : null}

      <section aria-labelledby="money-h">
        <h2 id="money-h">Money, last 24 hours</h2>
        <div>
          <Stat label="Collected" value={formatNaira(o.collected_kobo)} tone="good" />
          <Stat label="Payments" value={o.payments} />
          <Stat label="Unresolved" value={o.unresolved} tone={o.unresolved > 0 ? "warn" : undefined} />
          <Stat
            label="Ledger check"
            value={o.ledger_ok === null ? "Not run" : o.ledger_ok ? "Pass" : "Fail"}
            sub={o.ledger_checked_at ? stamp(o.ledger_checked_at) : undefined}
            tone={o.ledger_ok === false ? "bad" : o.ledger_ok ? "good" : undefined}
          />
        </div>
      </section>

      <section aria-labelledby="funnel-h">
        <h2 id="funnel-h">Funnel</h2>
        <div>
          <Stat label="Registered" value={o.registered} href="/admin/users" />
          <Stat label="Paid for verification" value={o.paid} />
          <Stat label="Conversion" value={`${o.conversion_percent}%`} />
          <Stat label="Clubs" value={o.clubs} sub={`${o.verified_clubs} verified`} href="/admin/clubs" />
          <Stat
            label="Review median, 30 days"
            value={o.review_median_hours === null ? "None yet" : `${o.review_median_hours}h`}
            sub={`Target ${REVIEW_TARGET_HOURS}h`}
            tone={o.review_median_hours !== null && o.review_median_hours > REVIEW_TARGET_HOURS ? "warn" : undefined}
          />
          <Stat label="LGAs open" value={o.live_lgas} />
        </div>
      </section>

      {o.clubs_waiting > 0 ? (
        <Flash variant="info" title={`${o.clubs_waiting} club ${o.clubs_waiting === 1 ? "review" : "reviews"} waiting`}>
          <a href="/admin/club-verification">Review clubs</a>
        </Flash>
      ) : null}
    </AdminShell>
  );
}

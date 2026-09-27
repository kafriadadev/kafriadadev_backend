import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AdminNav } from "@/components/AdminNav";
import { Flash } from "@/components/Flash";
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
          <div className="stack">
            <h1>Administrator</h1>
            <Flash variant="bad" title="You do not have access to this">
              <p style={{ marginBottom: 0 }}>Only a super administrator can open this.</p>
            </Flash>
          </div>
        );
      }
    }
    throw error;
  }

  return (
    <div className="stack">
      <AdminNav current="/admin" />
      <h1>Overview</h1>

      {o.ledger_ok === false ? (
        <Flash variant="bad" title="The ledger check failed">
          <p style={{ marginBottom: 0 }}>
            The last nightly check found a problem
            {o.ledger_checked_at ? ` (${stamp(o.ledger_checked_at)})` : ""}. Nothing else matters
            until it is resolved.
          </p>
        </Flash>
      ) : null}
      {o.unresolved > 0 ? (
        <Flash variant="warn" title={`${o.unresolved} unresolved ${o.unresolved === 1 ? "payment" : "payments"}`}>
          <p style={{ marginBottom: 0 }}>
            These need a person: the amount paid did not match what was agreed.
          </p>
        </Flash>
      ) : null}
      {o.review_median_hours !== null && o.review_median_hours > REVIEW_TARGET_HOURS ? (
        <Flash variant="warn" title="Reviews are slower than the target">
          <p style={{ marginBottom: 0 }}>
            The median decision took {o.review_median_hours} hours this month; the target is{" "}
            {REVIEW_TARGET_HOURS}.
          </p>
        </Flash>
      ) : null}

      <section className="doc" aria-label="Money, last 24 hours">
        <div className="doc__body">
          <p className="eyebrow">Money — last 24 hours</p>
          <dl className="facts">
            <div className="fact"><dt>Collected</dt><dd><span className="amount">{formatNaira(o.collected_kobo)}</span></dd></div>
            <div className="fact"><dt>Payments</dt><dd>{o.payments}</dd></div>
            <div className="fact"><dt>Unresolved</dt><dd>{o.unresolved}</dd></div>
            <div className="fact">
              <dt>Ledger check</dt>
              <dd>{o.ledger_ok === null ? "Not run yet" : o.ledger_ok ? "Pass" : "Fail"}</dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="doc" aria-label="Funnel">
        <div className="doc__body">
          <p className="eyebrow">Funnel</p>
          <dl className="facts">
            <div className="fact"><dt>Registered</dt><dd>{o.registered}</dd></div>
            <div className="fact"><dt>Paid for verification</dt><dd>{o.paid}</dd></div>
            <div className="fact"><dt>Conversion</dt><dd>{o.conversion_percent}%</dd></div>
            <div className="fact"><dt>Clubs</dt><dd>{o.clubs} ({o.verified_clubs} verified)</dd></div>
            <div className="fact">
              <dt>Review median, 30 days</dt>
              <dd>{o.review_median_hours === null ? "No decisions yet" : `${o.review_median_hours}h`}</dd>
            </div>
            <div className="fact"><dt>LGAs open</dt><dd>{o.live_lgas}</dd></div>
          </dl>
        </div>
      </section>

      {o.clubs_waiting > 0 ? (
        <Flash variant="info" title={`${o.clubs_waiting} club ${o.clubs_waiting === 1 ? "review" : "reviews"} waiting`}>
          <a href="/admin/club-verification" className="btn btn--primary">Review clubs</a>
        </Flash>
      ) : null}
    </div>
  );
}

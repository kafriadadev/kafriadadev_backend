import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { EmptyState } from "@/components/EmptyState";
import { PageHead } from "@/components/PageHead";
import { ApiError, type Payment, getMe, listPayments } from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";

export const metadata: Metadata = { title: "My payments" };
export const dynamic = "force-dynamic";

const PURPOSE_LABEL: Record<string, string> = {
  stage2_athlete: "Stage-2 verification",
  stage2_org: "Club verification",
};

const STATE_LABEL: Record<Payment["state"], string> = {
  confirmed: "Confirmed",
  checking: "Checking",
  review: "Needs a check",
  failed: "Not completed",
};

const STATE_PILL: Record<Payment["state"], string> = {
  confirmed: "pill pill--issued",
  checking: "pill pill--pending",
  review: "pill pill--pending",
  failed: "pill pill--bad",
};

const stamp = (iso: string): string =>
  new Date(iso).toLocaleString("en-GB", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lagos",
  });

/**
 * My payments (ATH-04).
 *
 * Every payment the athlete has ever started, newest first. A frozen payment
 * reads as "needs a check", same as it does on /pay — this screen never shows
 * the internal status, only what it means for the person reading it.
 */
export default async function PaymentsPage() {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  try {
    await getMe(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }

  const payments = await listPayments(token);

  return (
    <div className="page page--wide stack">
      <PageHead
        back={{ href: "/me", label: "My account" }}
        eyebrow="Account"
        title="My payments"
        app
      />

      {payments.length === 0 ? (
        <EmptyState title="Nothing here yet">
          <p className="small">You have not started a payment.</p>
          <a href="/pay" className="btn btn--primary">Get verified for ₦2,500</a>
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Payment</th><th>Date</th><th>Reference</th><th>Status</th><th className="num">Amount</th></tr>
            </thead>
            <tbody>
              {payments.map((p) => (
                <tr key={p.reference}>
                  <td data-label=""><strong>{PURPOSE_LABEL[p.purpose] ?? p.purpose}</strong></td>
                  <td data-label="Date"><span className="nowrap">{stamp(p.created_at)}</span></td>
                  <td data-label="Reference"><span className="kuid small">{p.reference}</span></td>
                  <td data-label="Status"><span className={STATE_PILL[p.state]}>{STATE_LABEL[p.state]}</span></td>
                  <td data-label="Amount" className="num"><strong>{formatNaira(p.amount_kobo)}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

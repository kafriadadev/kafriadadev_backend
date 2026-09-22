import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ApiError, type Payment, getMe, listPayments } from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";

export const metadata: Metadata = { title: "My payments" };
export const dynamic = "force-dynamic";

const PURPOSE_LABEL: Record<string, string> = {
  stage2_athlete: "Stage-2 verification",
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
    <div className="stack">
      <p className="eyebrow">Account</p>
      <h1>My payments</h1>

      {payments.length === 0 ? (
        <div className="notice" role="status">
          <p className="notice__title">Nothing here yet</p>
          <p style={{ marginBottom: 0 }}>
            You have not started a payment. <a href="/pay">Get verified</a> starts
            one for ₦2,500.
          </p>
        </div>
      ) : (
        <div className="stack" style={{ gap: "var(--s3)" }}>
          {payments.map((p) => (
            <section key={p.reference} className="doc" aria-label={`Payment ${p.reference}`}>
              <div className="doc__body" style={{ display: "flex", justifyContent: "space-between", gap: "var(--s4)", flexWrap: "wrap", alignItems: "flex-start" }}>
                <div style={{ minWidth: 0 }}>
                  <p style={{ margin: 0, fontWeight: 700 }}>
                    {PURPOSE_LABEL[p.purpose] ?? p.purpose}
                  </p>
                  <p className="hint" style={{ margin: "2px 0 0" }}>{stamp(p.created_at)}</p>
                  <p className="kuid" style={{ fontSize: ".8rem", marginTop: "var(--s2)" }}>
                    {p.reference}
                  </p>
                </div>
                <div style={{ textAlign: "right", flex: "none" }}>
                  <p className="amount" style={{ margin: 0 }}>{formatNaira(p.amount_kobo)}</p>
                  <span className={STATE_PILL[p.state]} style={{ marginTop: "var(--s2)" }}>
                    {STATE_LABEL[p.state]}
                  </span>
                </div>
              </div>
            </section>
          ))}
        </div>
      )}

      <p className="hint"><a href="/me">Back to my account</a></p>
    </div>
  );
}

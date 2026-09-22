import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Flash } from "@/components/Flash";
import {
  ApiError,
  type AdminPaymentLookup,
  findPaymentByReference,
  getMe,
} from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";
import { reverseAction } from "./actions";

export const metadata: Metadata = { title: "Record a refund" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending — never reached Paystack, or still checking",
  success: "Settled",
  failed: "Failed",
  frozen: "Frozen — amount mismatch, needs a person",
  abandoned: "Abandoned",
};

/**
 * Record a refund (ADM-04).
 *
 * This RECORDS a refund made by hand in Paystack's own dashboard — there is
 * no payout path and nothing here calls Paystack. Same two-step shape as
 * /admin/revoke: look up, then confirm with a reason and a password, because
 * this is the one screen that writes an amount into the ledger by hand.
 */
export default async function ReversalPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let me;
  try {
    me = await getMe(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }
  if (!me.roles.some((r) => r.role === "super_admin")) {
    return (
      <div className="stack">
        <h1>Record a refund</h1>
        <Flash variant="bad" title="You do not have access to this">
          <p style={{ marginBottom: 0 }}>Only a super administrator can record a refund.</p>
        </Flash>
      </div>
    );
  }

  const reference = one(params.reference).trim();
  const error = one(params.error);
  const done = one(params.done);

  let found: AdminPaymentLookup | null = null;
  let lookupError: string | null = null;
  if (reference && !done) {
    try {
      found = await findPaymentByReference(token, reference);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        lookupError = "No payment is on file with that reference.";
      } else if (caught instanceof ApiError) {
        lookupError = caught.message;
      } else {
        throw caught;
      }
    }
  }

  return (
    <div className="stack">
      <p className="eyebrow">Admin &middot; ADM-04</p>
      <h1>Record a refund</h1>
      <p className="lede">
        Finds a payment by its reference, so a refund already made in the
        Paystack dashboard can be recorded against it. This never moves money —
        it only makes the ledger match the bank.
      </p>

      {done ? (
        <Flash variant="good" title="Recorded">
          <p style={{ marginBottom: 0 }}>
            The refund for <span className="kuid">{done}</span> is recorded in
            the ledger. It cannot be recorded again against the same payment.
          </p>
        </Flash>
      ) : null}

      {error ? (
        <Flash variant="bad" title="That did not work">
          <p style={{ marginBottom: 0 }}>{error}</p>
        </Flash>
      ) : null}

      <form method="GET" className="doc" noValidate>
        <div className="doc__body">
          <div className="field">
            <label htmlFor="reference">Payment reference</label>
            <span className="hint">From the Paystack dashboard. Starts with KAF-.</span>
            <input
              id="reference"
              name="reference"
              required
              placeholder="KAF-…"
              defaultValue={reference}
              style={{ fontFamily: "var(--font-mono)" }}
            />
          </div>
          <button type="submit" className="btn btn--primary btn--block">Find</button>
        </div>
      </form>

      {lookupError ? (
        <Flash variant="warn" title="Not found">
          <p style={{ marginBottom: 0 }}>{lookupError}</p>
        </Flash>
      ) : null}

      {found ? (
        <section className="doc" aria-label="What was found">
          <div className="doc__body">
            <dl className="facts">
              <div className="fact"><dt>Reference</dt><dd><span className="kuid">{found.reference}</span></dd></div>
              <div className="fact"><dt>Paid by</dt><dd>{found.payer_name}</dd></div>
              {found.athlete_kuid ? (
                <div className="fact">
                  <dt>For</dt>
                  <dd>{found.athlete_name} &middot; <span className="kuid">{found.athlete_kuid}</span></dd>
                </div>
              ) : null}
              <div className="fact"><dt>Purpose</dt><dd>{found.purpose}</dd></div>
              <div className="fact">
                <dt>Status</dt>
                <dd>{STATUS_LABEL[found.status] ?? found.status}</dd>
              </div>
              <div className="fact">
                <dt>Amount settled</dt>
                <dd>{found.gross_kobo !== null ? formatNaira(found.gross_kobo) : "—"}</dd>
              </div>
              {found.already_reversed ? (
                <div className="fact"><dt>Refund</dt><dd>Already recorded</dd></div>
              ) : null}
            </dl>

            {found.reversible ? (
              <form action={reverseAction} style={{ marginTop: "var(--s5)" }}>
                <input type="hidden" name="reference" value={found.reference} />
                <div className="field">
                  <label htmlFor="amount_naira">Amount refunded</label>
                  <span className="hint">
                    In naira, exactly as it left the account
                    {found.gross_kobo !== null ? ` — up to ${formatNaira(found.gross_kobo)}` : ""}.
                  </span>
                  <input
                    id="amount_naira"
                    name="amount_naira"
                    type="number"
                    min="0.01"
                    step="0.01"
                    inputMode="decimal"
                    required
                  />
                </div>
                <div className="field">
                  <label htmlFor="reason">Reason</label>
                  <span className="hint">Kept permanently with the ledger line.</span>
                  <textarea id="reason" name="reason" maxLength={1000} required />
                </div>
                <div className="field">
                  <label htmlFor="current_password">Your password</label>
                  <span className="hint">Confirms this is really you.</span>
                  <input
                    id="current_password"
                    name="current_password"
                    type="password"
                    autoComplete="current-password"
                    required
                  />
                </div>
                <button type="submit" className="btn btn--primary btn--block">
                  Record this refund
                </button>
              </form>
            ) : (
              <p className="hint" style={{ marginTop: "var(--s4)", marginBottom: 0 }}>
                Nothing to record — only a settled payment with no refund on it
                already can have one recorded.
              </p>
            )}
          </div>
        </section>
      ) : null}
    </div>
  );
}

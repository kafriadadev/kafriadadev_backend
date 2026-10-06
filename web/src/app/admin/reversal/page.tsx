import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PageHead } from "@/components/PageHead";
import { NoAccess } from "@/components/NoAccess";
import { AdminShell } from "@/components/AdminNav";
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
      <NoAccess title="Record a refund" message="Only a super administrator can record a refund." />
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
    <AdminShell current="/admin/reversal">
      <PageHead
        eyebrow="Administrator"
        title="Record a refund"
        lede="Finds a payment by its reference, so a refund already made in the
        Paystack dashboard can be recorded against it. This never moves money —
        it only makes the ledger match the bank."
        app
      />

      {done ? (
        <Flash variant="good" title="Recorded">
          <p>
            The refund for <span>{done}</span> is recorded in
            the ledger. It cannot be recorded again against the same payment.
          </p>
        </Flash>
      ) : null}

      {error ? (
        <Flash variant="bad" title="That did not work">
          <p>{error}</p>
        </Flash>
      ) : null}

      <form method="GET" role="search" noValidate>
        <div>
          <label htmlFor="reference">Payment reference</label>
          <span>From the Paystack dashboard. Starts with KAF-.</span>
          <input
            id="reference"
            name="reference"
            required
            placeholder="KAF-…"
            defaultValue={reference}
          />
        </div>
        <button type="submit">Find</button>
      </form>

      {lookupError ? (
        <Flash variant="warn" title="Not found">
          <p>{lookupError}</p>
        </Flash>
      ) : null}

      {found ? (
        <section aria-label="What was found">
          <div>
            <dl>
              <div><dt>Reference</dt><dd><span>{found.reference}</span></dd></div>
              <div><dt>Paid by</dt><dd>{found.payer_name}</dd></div>
              {found.athlete_kuid ? (
                <div>
                  <dt>For</dt>
                  <dd>{found.athlete_name} &middot; <span>{found.athlete_kuid}</span></dd>
                </div>
              ) : null}
              <div><dt>Purpose</dt><dd>{found.purpose}</dd></div>
              <div>
                <dt>Status</dt>
                <dd>{STATUS_LABEL[found.status] ?? found.status}</dd>
              </div>
              <div>
                <dt>Amount settled</dt>
                <dd>{found.gross_kobo !== null ? formatNaira(found.gross_kobo) : "—"}</dd>
              </div>
              {found.already_reversed ? (
                <div><dt>Refund</dt><dd>Already recorded</dd></div>
              ) : null}
            </dl>

            {found.reversible ? (
              <form action={reverseAction}>
                <input type="hidden" name="reference" value={found.reference} />
                <div>
                  <label htmlFor="amount_naira">Amount refunded</label>
                  <span>
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
                <div>
                  <label htmlFor="reason">Reason</label>
                  <span>Kept permanently with the ledger line.</span>
                  <textarea id="reason" name="reason" maxLength={1000} required />
                </div>
                <div>
                  <label htmlFor="current_password">Your password</label>
                  <span>Confirms this is really you.</span>
                  <input
                    id="current_password"
                    name="current_password"
                    type="password"
                    autoComplete="current-password"
                    required
                  />
                </div>
                <button type="submit">
                  Record this refund
                </button>
              </form>
            ) : (
              <p>
                Nothing to record — only a settled payment with no refund on it
                already can have one recorded.
              </p>
            )}
          </div>
        </section>
      ) : null}
    </AdminShell>
  );
}

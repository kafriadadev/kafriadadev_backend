import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PageHead } from "@/components/PageHead";
import { NoAccess } from "@/components/NoAccess";
import { Flash } from "@/components/Flash";
import { SubmitButton } from "@/components/SubmitButton";
import {
  ApiError,
  type ClubVerification,
  type Payment,
  getClubVerification,
  getPayment,
} from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";
import { resubmitClubAction, startClubPaymentAction, uploadDocumentAction } from "./actions";

export const metadata: Metadata = { title: "Verify your club" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

const DOCUMENT_LABEL: Record<string, string> = {
  ready: "Added",
  uploaded: "Received — getting it ready",
  pending: "Received — getting it ready",
  unreadable: "We could not read that file — please send another",
};

/**
 * Verify a club (CLB-04): the club's registration document or LGA letter, one payment,
 * and an administrator's decision. Every rule — that the club is approved, that a
 * document is ready before anyone can pay, what the price is — is the API's; this screen
 * shows the state it reports and forwards the three actions.
 */
export default async function VerifyClubPage({
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

  let v: ClubVerification;
  try {
    v = await getClubVerification(token, id);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403 || error.status === 404) {
        return (
          <NoAccess title="Verify your club" message="You can only verify a club you administer." />
        );
      }
    }
    throw error;
  }

  const reference = one(query.reference);
  let payment: Payment | null = null;
  if (reference) {
    try {
      payment = await getPayment(token, reference);
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 404) throw error;
    }
  }

  const base = `/clubs/${encodeURIComponent(id)}`;
  const error = one(query.error);
  const ready = v.document === "ready";

  return (
    <div className="page stack">
      <PageHead
        back={{ href: base, label: "Club" }}
        eyebrow={<>Club &middot; {v.club_name}</>}
        title="Verify your club"
      />

      {error ? (
        <Flash variant="bad" title="That did not work">
          <p className="mb0">{error}</p>
        </Flash>
      ) : null}
      {one(query.saved) ? (
        <Flash variant="good" title="Document saved">
          <p className="mb0">You can pay now.</p>
        </Flash>
      ) : null}

      {payment ? <PaymentNotice payment={payment} club={id} /> : null}

      {v.verified ? (
        <Flash variant="good" title="This club is verified">
          <p className="mb0">The verified badge shows on your club page.</p>
        </Flash>
      ) : v.club_status !== "approved" ? (
        <Flash variant="warn" title="Waiting for approval">
          <p className="mb0">A club must be approved before it can be verified.</p>
        </Flash>
      ) : v.state === "under_review" ? (
        <Flash variant="info" title="Your club is being reviewed">
          <p className="mb0">
            An administrator is checking your document. You will be told as soon as it is decided.
          </p>
        </Flash>
      ) : (
        <>
          <section className="doc" aria-label="What you get">
            <div className="doc__body">
              <p className="eyebrow">Verified club</p>
              <ul className="bullets">
                <li>A verified badge on your club page</li>
                <li>Checked by a KAFRIADA administrator</li>
              </ul>
              <dl className="facts">
                <div className="fact">
                  <dt>One payment. No renewal.</dt>
                  <dd><span className="amount">{formatNaira(v.price_kobo)}</span></dd>
                </div>
              </dl>
            </div>
          </section>

          {v.state === "rejected" && v.reason ? (
            <Flash variant="bad" title="Not verified this time">
              <p className="mb0">{v.reason}</p>
            </Flash>
          ) : null}

          <h2>{v.state === "rejected" ? "Send a better document" : "Step 1 of 2 — your document"}</h2>
          <form action={uploadDocumentAction} encType="multipart/form-data" className="doc">
            <div className="doc__body">
              <input type="hidden" name="club" value={id} />
              <div className="field">
                <label htmlFor="document">Club registration or LGA letter</label>
                <span className="hint">A clear photo or scan of the whole page.</span>
                <input id="document" name="document" type="file" accept="image/jpeg,image/png,image/webp" />
                <span className="hint">
                  {v.document ? (DOCUMENT_LABEL[v.document] ?? "Added") : "Not added yet"}
                </span>
              </div>
              <SubmitButton
                className="btn btn--ghost btn--block"
                pending="Uploading your document…"
                detail="Please keep this page open. This can take a few seconds."
              >
                Save my document
              </SubmitButton>
              <p className="hint mt-4 mb0">
                Maximum 10MB. The document is used only to check the club.
              </p>
            </div>
          </form>

          {v.state === "rejected" ? (
            <form action={resubmitClubAction}>
              <input type="hidden" name="club" value={id} />
              <SubmitButton disabled={!ready} pending="Sending for review…">
                Send for review again
              </SubmitButton>
              <p className="hint">The payment you already made covers this. You do not pay again.</p>
            </form>
          ) : (
            <>
              <h2>Step 2 of 2 — pay</h2>
              {v.paid ? (
                <p className="hint">This club has already paid. Nothing more is due.</p>
              ) : (
                <form action={startClubPaymentAction}>
                  <input type="hidden" name="club" value={id} />
                  <SubmitButton
                    disabled={!ready}
                    pending="Taking you to Paystack…"
                    detail="Please do not close or refresh this page."
                  >
                    Pay {formatNaira(v.price_kobo)} with Paystack
                  </SubmitButton>
                  <p className="hint form-foot">
                    {ready
                      ? "You will leave KAFRIADA to pay. We never see your card details."
                      : "Add your document first."}
                  </p>
                </form>
              )}
            </>
          )}
        </>
      )}

    </div>
  );
}

function PaymentNotice({ payment, club }: { payment: Payment; club: string }) {
  const again = `/clubs/${encodeURIComponent(club)}/verify?reference=${encodeURIComponent(payment.reference)}`;
  if (payment.state === "confirmed") {
    return (
      <Flash variant="good" title="Payment confirmed">
        <p className="mb0">
          We received {formatNaira(payment.amount_kobo)}. Your club is now with an administrator.
        </p>
      </Flash>
    );
  }
  if (payment.state === "checking") {
    return (
      <Flash variant="info" title="We are confirming your payment with Paystack">
        <p>This usually takes a few seconds. You can close this page safely.</p>
        <a href={again} className="btn btn--ghost">Check again</a>
      </Flash>
    );
  }
  if (payment.state === "review") {
    return (
      <Flash variant="warn" title="Your payment needs a check by our team">
        <p className="mb0">
          Please do not pay again. We will contact you on the phone number you registered with.
        </p>
      </Flash>
    );
  }
  return (
    <Flash variant="bad" title="The payment was not completed">
      <p className="mb0">
        If money left your account, it will show here as confirmed once Paystack tells us.
        Otherwise you can try again below.
      </p>
    </Flash>
  );
}

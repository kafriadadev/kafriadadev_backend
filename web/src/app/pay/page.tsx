import { SubmitButton } from "@/components/SubmitButton";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import {
  ApiError,
  getPayment,
  getPaymentQuote,
  getVerification,
  type Payment,
  type PaymentQuote,
} from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";
import { startPaymentAction } from "./actions";

export const metadata: Metadata = { title: "Pay for verification" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/** After this long "checking" stops being a few seconds and is worth saying so. */
const STILL_CHECKING_MS = 2 * 60 * 1000;

/**
 * Payment (VER-03): leaving for Paystack, and coming back.
 *
 * One address for both halves. With no `reference` it is the price and the
 * button; Paystack sends the person back to it with `?reference=`, and then it
 * reads our own record of that payment.
 *
 * **This screen grants nothing.** It shows what the API recorded, and the API
 * only records what Paystack's signed webhook told it. Arriving here with a
 * reference proves nothing, so a person cannot type their way to "confirmed".
 * "Check again" is a plain link that reloads the page: no polling, because on a
 * slow network a polling page is worse than a button, and on Opera Mini it does
 * not run at all.
 */
export default async function PayPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const params = await searchParams;
  const reference = one(params.reference);
  const error = one(params.error);

  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  try {
    return reference ? await returned(token, reference) : await start(token, error);
  } catch (caught) {
    if (caught instanceof ApiError && caught.status === 401) redirect("/sign-in?ended=1");
    throw caught;
  }
}

async function start(token: string, error: string) {
  let quote: PaymentQuote | null = null;
  let problem = error;
  try {
    quote = await getPaymentQuote(token);
    // Nothing to pay for until there is something for a reviewer to look at: the
    // API would refuse the payment anyway, and saying so here saves the trip.
    const verification = await getVerification(token);
    if (!quote.already_paid && !verification.ready_to_pay) redirect("/verify");
  } catch (caught) {
    // No athlete record, or the API is away: say so, and do not offer a button.
    if (!(caught instanceof ApiError) || caught.status === 401) throw caught;
    problem = problem || caught.message;
  }

  return (
    <div className="stack">
      <p className="eyebrow">Verification</p>
      <h1>Payment</h1>

      {problem ? (
        <div className="notice notice--bad" role="alert" tabIndex={-1}>
          <p className="notice__title">We could not start your payment</p>
          <p style={{ marginBottom: 0 }}>{problem}</p>
        </div>
      ) : null}

      {quote ? (
        <section className="doc" aria-label="Amount due">
          <div className="doc__body">
            <dl className="facts">
              <div className="fact">
                <dt>Amount due</dt>
                <dd><span className="amount">{formatNaira(quote.amount_kobo)}</span></dd>
              </div>
              <div className="fact">
                <dt>For</dt>
                <dd>
                  Athlete verification · <span className="kuid">{quote.kuid}</span>
                </dd>
              </div>
            </dl>

            {quote.already_paid ? (
              <p className="hint">You have already paid for this. Nothing more is due.</p>
            ) : (
              <form action={startPaymentAction}>
                <SubmitButton pending="Taking you to Paystack…" detail="Please do not close or refresh this page.">
                  Pay securely with Paystack
                </SubmitButton>
                <p className="hint" style={{ textAlign: "center", marginTop: "var(--s4)" }}>
                  You will leave KAFRIADA to pay. We never see your card details.
                </p>
              </form>
            )}
          </div>
        </section>
      ) : null}

      <p><a href="/me">Back to my account</a></p>
    </div>
  );
}

async function returned(token: string, reference: string) {
  let payment: Payment;
  try {
    payment = await getPayment(token, reference);
  } catch (caught) {
    if (caught instanceof ApiError && caught.status === 404) {
      return (
        <div className="stack">
          <h1>Payment</h1>
          <div className="notice notice--warn" role="status">
            <p className="notice__title">We could not find that payment</p>
            <p style={{ marginBottom: 0 }}>
              It may belong to another account. <a href="/pay">Start again</a>
            </p>
          </div>
        </div>
      );
    }
    throw caught;
  }

  const again = `/pay?reference=${encodeURIComponent(payment.reference)}`;
  const age = Date.now() - new Date(payment.created_at).getTime();
  const amount = formatNaira(payment.amount_kobo);

  return (
    <div className="stack">
      <p className="eyebrow">Verification</p>
      <h1>Payment</h1>

      {payment.state === "confirmed" ? (
        <div className="notice notice--good" role="status">
          <p className="notice__title">Payment confirmed</p>
          <p>
            We received <span className="amount">{amount}</span>. Thank you.
          </p>
          <a href="/verify" className="btn btn--primary">See my verification</a>
        </div>
      ) : payment.state === "checking" ? (
        <div className="notice" role="status">
          <p className="notice__title">We are confirming your payment with Paystack</p>
          <p>
            {age > STILL_CHECKING_MS
              ? "This is taking longer than usual. There is no need to keep refreshing."
              : "This usually takes a few seconds."}{" "}
            You can close this page safely: when the payment is confirmed it will
            show here.
          </p>
          <a href={again} className="btn btn--ghost">Check again</a>
        </div>
      ) : payment.state === "review" ? (
        <div className="notice notice--warn" role="status">
          <p className="notice__title">Your payment needs a check by our team</p>
          <p style={{ marginBottom: 0 }}>
            Please do not pay again. We will contact you on the phone number you
            registered with.
          </p>
        </div>
      ) : (
        <div className="notice notice--bad" role="status">
          <p className="notice__title">The payment was not completed</p>
          <p>
            If money left your account, it will show here as confirmed once
            Paystack tells us. Otherwise you can try again.
          </p>
          <div style={{ display: "flex", gap: "var(--s3)", flexWrap: "wrap" }}>
            <a href="/pay" className="btn btn--primary">Try again</a>
            <a href={again} className="btn btn--ghost">Check again</a>
          </div>
        </div>
      )}
    </div>
  );
}

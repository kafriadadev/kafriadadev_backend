import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Flash } from "@/components/Flash";
import { ResendCountdown } from "@/components/ResendCountdown";
import { getMe } from "@/lib/api";
import { pending, sessionToken } from "@/lib/session";
import { confirmPhoneAction, resendCodeAction } from "./actions";

export const metadata: Metadata = { title: "Confirm your phone" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/**
 * Confirm your phone (AUT-02).
 *
 * **The ID already exists by this point.** Registration mints it; only the
 * confirmed flag waits here. So a provider outage delays a confirmation, never
 * a registration — which is what you want in a hall with 200 people in it, and
 * why there is a plain link to the card on this page.
 *
 * One input, not six boxes: a six-box widget needs JavaScript, and this screen
 * has to work without it.
 */
export default async function ConfirmPhonePage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const params = await searchParams;
  const error = one(params.error);
  const sent = one(params.sent);
  const wait = one(params.wait);

  // Either they have just registered (the pending cookie) or they are signed in
  // with a number that was never confirmed.
  const waiting = await pending();
  const token = await sessionToken();
  const me = token ? await getMe(token).catch(() => null) : null;
  if (!waiting && !me) redirect("/sign-in");
  if (!waiting && me?.phone_verified) redirect("/me");

  const phone = waiting?.phone ?? "";
  const shown = me?.phone ?? phone;
  const kuid = waiting?.kuid || me?.kuid || "";
  // A pilot stand-in for SMS while Twilio is not yet registered (settings
  // otp_channel). Remove this branch once codes go by text message again.
  const emailSentTo = waiting?.email;

  return (
    <div className="stack">
      <p className="eyebrow">Step 2 of 3</p>
      <h1>Enter the code we sent</h1>
      <p className="lede">
        {emailSentTo
          ? `Sent by email to ${emailSentTo}.`
          : `Sent by text message to ${shown}.`}
      </p>

      {error ? (
        <Flash variant="bad" title="That did not work">
          <p style={{ marginBottom: 0 }}>{error}</p>
        </Flash>
      ) : sent ? (
        <Flash variant="good" title="Another code is on its way" autoDismissMs={8000}>
          <p style={{ marginBottom: 0 }}>Check your messages — the timer below shows when you can ask again.</p>
        </Flash>
      ) : null}

      <form action={confirmPhoneAction} className="doc" noValidate>
        <div className="doc__body">
          <input type="hidden" name="phone" value={phone} />
          <div className="field">
            <label htmlFor="code">6-digit code</label>
            <span className="hint" id="code-hint">
              It expires in 10 minutes. We will never ask you for it.
            </span>
            <input
              id="code"
              name="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              maxLength={6}
              placeholder="000000"
              aria-describedby="code-hint"
              style={{ fontFamily: "var(--font-mono)", letterSpacing: ".3em" }}
            />
          </div>
          <button type="submit" className="btn btn--primary btn--block">
            Confirm my number
          </button>
        </div>
      </form>

      <ResendCountdown seconds={sent ? Number(wait) || 60 : 0}>
        <form action={resendCodeAction}>
          <input type="hidden" name="phone" value={phone} />
          <button type="submit" className="btn btn--ghost">Send another code</button>
        </form>
      </ResendCountdown>

      <div className="notice">
        <p className="notice__title">Your ID is already yours</p>
        <p style={{ marginBottom: kuid ? "var(--s3)" : 0 }}>
          Confirming your number is how we know the phone is yours, and it is
          needed before you can be verified. It does not affect your KAFRIADA ID,
          which was issued the moment you registered.
        </p>
        {kuid ? (
          <a href={`/card/${encodeURIComponent(kuid)}`}>See my card now</a>
        ) : null}
      </div>

      <p className="hint" style={{ color: "var(--muted)" }}>
        Wrong number? <a href="/register">Start again with the right one</a>.
      </p>
    </div>
  );
}

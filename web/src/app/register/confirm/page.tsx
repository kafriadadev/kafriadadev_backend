import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Flash } from "@/components/Flash";
import { PageHead } from "@/components/PageHead";
import { ResendCountdown } from "@/components/ResendCountdown";
import { SubmitButton } from "@/components/SubmitButton";
import { pending } from "@/lib/session";
import { confirmEmailAction, resendCodeAction } from "./actions";

export const metadata: Metadata = { title: "Confirm your email" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/**
 * Confirm your email. Reached straight after registering, or after signing in
 * to an account whose email was never confirmed; both set the pending cookie.
 * There is no session until the code is accepted.
 *
 * One input, not six boxes: a six-box widget needs JavaScript, and this screen
 * has to work without it.
 */
export default async function ConfirmEmailPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const params = await searchParams;
  const error = one(params.error);
  const sent = one(params.sent);
  const wait = one(params.wait);

  const waiting = await pending();
  if (!waiting) redirect("/sign-in");
  const sentTo = waiting.email || "your email address";

  return (
    <div>
      <PageHead
        eyebrow="Confirm your email"
        title="Enter the code we emailed"
        lede={`Sent to ${sentTo}. Check your spam folder if it has not arrived within a few minutes.`}
      />

      {error ? (
        <Flash variant="bad" title="That did not work">
          <p>{error}</p>
        </Flash>
      ) : sent ? (
        <Flash variant="good" title="Another code is on its way" autoDismissMs={8000}>
          <p>Check your email. The timer below shows when you can ask again.</p>
        </Flash>
      ) : null}

      <form action={confirmEmailAction} noValidate>
        <div>
          <div>
            <label htmlFor="code">6-digit code</label>
            <span id="code-hint">
              It expires in 10 minutes. KAFRIADA NET will never ask you for it.
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
            />
          </div>
          <SubmitButton pending="Checking your code…">Confirm my email</SubmitButton>
        </div>
      </form>

      <ResendCountdown seconds={sent ? Number(wait) || 60 : 0}>
        <form action={resendCodeAction}>
          <button type="submit">Send another code</button>
        </form>
      </ResendCountdown>

      <div>
        <p>Why we ask</p>
        <p>
          Your account opens once your email is confirmed. We use it for receipts,
          verification decisions and to help you back in if you forget your password.
        </p>
      </div>
    </div>
  );
}

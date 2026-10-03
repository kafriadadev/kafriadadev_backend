import type { Metadata } from "next";

import { PageHead } from "@/components/PageHead";
import { Flash } from "@/components/Flash";
import { resetPasswordAction, sendResetCodeAction } from "./actions";

export const metadata: Metadata = { title: "Reset your password" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/**
 * Forgot password (AUT-05). Two steps on one address, each a plain POST.
 *
 * The phone number is the identity anchor, so it is what recovers an account.
 * Step two ends every other session: if the reason for the reset was that
 * somebody else had the account, leaving their session alive would be pointless.
 */
export default async function ForgotPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const params = await searchParams;
  const error = one(params.error);
  const sent = one(params.sent);
  const phone = one(params.phone);

  return (
    <div className="auth stack">
      <PageHead
        eyebrow="Account recovery"
        title="Reset your password"
      />

      {error ? (
        <Flash variant="bad" title="That did not work">
          <p className="mb0">{error}</p>
        </Flash>
      ) : null}

      {!sent ? (
        <>
          <p className="lede">
            We&apos;ll send a code to confirm it&apos;s you.
          </p>
          <form action={sendResetCodeAction} className="doc" noValidate>
            <div className="doc__body">
              <div className="field">
                <label htmlFor="phone">Phone number</label>
                <input
                  id="phone"
                  name="phone"
                  type="tel"
                  inputMode="tel"
                  required
                  placeholder="0803 000 0000"
                  autoComplete="tel"
                  defaultValue={phone}
                />
              </div>
              <button type="submit" className="btn btn--primary btn--block">
                Send code
              </button>
            </div>
          </form>
        </>
      ) : (
        <>
          <Flash title="Check your messages">
            <p className="mb0">
              If that number has a KAFRIADA account, a code is on its way to it.
              The code expires in 10 minutes.
            </p>
          </Flash>

          <form action={resetPasswordAction} className="doc" noValidate>
            <div className="doc__body">
              <input type="hidden" name="phone" value={phone} />
              <div className="field">
                <label htmlFor="code">6-digit code</label>
                <input
                  id="code"
                  name="code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  required
                  maxLength={6}
                  placeholder="000000"
                  className="code-input"
                />
              </div>
              <div className="field">
                <label htmlFor="new_password">New password</label>
                <span className="hint" id="new-pw-hint">
                  At least 10 characters. A short phrase you will remember is
                  better than a short word with symbols in it.
                </span>
                <input
                  id="new_password"
                  name="new_password"
                  type="password"
                  required
                  minLength={10}
                  autoComplete="new-password"
                  aria-describedby="new-pw-hint"
                />
              </div>
              <button type="submit" className="btn btn--primary btn--block">
                Set new password
              </button>
              <p className="hint form-foot">
                Every device signed in to this account will be signed out.
              </p>
            </div>
          </form>
        </>
      )}

      <p className="hint muted">
        Remembered it? <a href="/sign-in">Sign in</a>.
      </p>
    </div>
  );
}

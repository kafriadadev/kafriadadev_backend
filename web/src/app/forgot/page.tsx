import type { Metadata } from "next";

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
    <div className="stack">
      <p className="eyebrow">Account recovery</p>
      <h1>Reset your password</h1>

      {error ? (
        <div className="notice notice--bad" role="alert" tabIndex={-1}>
          <p className="notice__title">That did not work</p>
          <p style={{ marginBottom: 0 }}>{error}</p>
        </div>
      ) : null}

      {!sent ? (
        <>
          <p className="lede">
            We send a code to your registered phone number.
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
          <div className="notice" role="status">
            <p className="notice__title">Check your messages</p>
            <p style={{ marginBottom: 0 }}>
              If that number has a KAFRIADA account, a code is on its way to it.
              The code expires in 10 minutes.
            </p>
          </div>

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
                  style={{ fontFamily: "var(--font-mono)", letterSpacing: ".3em" }}
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
              <p className="hint" style={{ textAlign: "center", marginTop: "var(--s4)" }}>
                Every device signed in to this account will be signed out.
              </p>
            </div>
          </form>
        </>
      )}

      <p className="hint" style={{ color: "var(--muted)" }}>
        Remembered it? <a href="/sign-in">Sign in</a>.
      </p>
    </div>
  );
}

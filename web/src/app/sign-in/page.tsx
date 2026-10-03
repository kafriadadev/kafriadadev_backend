import { PageHead } from "@/components/PageHead";
import { SubmitButton } from "@/components/SubmitButton";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Flash } from "@/components/Flash";
import { getMe } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { signInAction } from "./actions";

export const metadata: Metadata = { title: "Sign in" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/**
 * Sign in (AUT-04). One screen for every role — athletes, club admins and
 * coordinators all sign in here, and the role decides how long they stay
 * signed in, not a "remember me" box.
 *
 * A wrong phone and a wrong password get the same message, which the API
 * decides. The form does not guess which half was wrong either.
 */
export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const params = await searchParams;
  const error = one(params.error);
  const ended = one(params.ended);
  const reset = one(params.reset);
  const needEmail = one(params.need_email) === "1";

  // Already signed in: go straight to the account page.
  const token = await sessionToken();
  if (token) {
    const me = await getMe(token).catch(() => null);
    if (me) redirect("/me");
  }

  return (
    <div className="auth stack">
      <PageHead
        eyebrow="Welcome back"
        title="Sign in"
      />

      {error ? (
        <Flash variant="bad" title="We could not sign you in">
          <p className="mb0">{error}</p>
        </Flash>
      ) : reset ? (
        <Flash variant="good" title="Your password is changed">
          <p className="mb0">
            Sign in with your new password. Every other device was signed out.
          </p>
        </Flash>
      ) : ended ? (
        <Flash title="You were signed out">
          <p className="mb0">
            Your session ended. Sign in again to continue.
          </p>
        </Flash>
      ) : null}

      <form action={signInAction} className="doc" noValidate>
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
              defaultValue={one(params.phone)}
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              required
              autoComplete="current-password"
            />
          </div>

          {needEmail ? (
            <div className="field field--error">
              <label htmlFor="email">Email</label>
              <span className="hint" id="email-hint">
                Your account has no email yet. We will send a code to confirm it.
              </span>
              <input id="email" name="email" type="email" required autoComplete="email"
                aria-describedby="email-hint" />
            </div>
          ) : null}

          <SubmitButton pending="Signing you in…">Sign in</SubmitButton>

          <p className="hint form-foot">
            <a href="/forgot">Forgot your password?</a>
          </p>
          <p className="hint center mt-2">
            No account yet? <a href="/register">Register free</a>
          </p>
        </div>
      </form>
    </div>
  );
}

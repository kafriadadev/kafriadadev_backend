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

  // Already signed in: go straight to the account page.
  const token = await sessionToken();
  if (token) {
    const me = await getMe(token).catch(() => null);
    if (me) redirect("/me");
  }

  return (
    <div className="stack">
      <p className="eyebrow">Welcome back</p>
      <h1>Sign in</h1>

      {error ? (
        <Flash variant="bad" title="We could not sign you in">
          <p style={{ marginBottom: 0 }}>{error}</p>
        </Flash>
      ) : reset ? (
        <Flash variant="good" title="Your password is changed">
          <p style={{ marginBottom: 0 }}>
            Sign in with your new password. Every other device was signed out.
          </p>
        </Flash>
      ) : ended ? (
        <Flash title="You were signed out">
          <p style={{ marginBottom: 0 }}>
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

          <button type="submit" className="btn btn--primary btn--block">
            Sign in
          </button>

          <p className="hint" style={{ textAlign: "center", marginTop: "var(--s4)" }}>
            <a href="/forgot">Forgot your password?</a>
          </p>
          <p className="hint" style={{ textAlign: "center", marginTop: "var(--s2)" }}>
            No account yet? <a href="/register">Register free</a>
          </p>
        </div>
      </form>
    </div>
  );
}

import type { Metadata } from "next";
import { redirect } from "next/navigation";

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

  return (
    <div className="stack">
      <p className="eyebrow">Step 2 of 3</p>
      <h1>Enter the code we sent</h1>
      <p className="lede">
        Sent by text message to {shown}.
      </p>

      {error ? (
        <div className="notice notice--bad" role="alert" tabIndex={-1}>
          <p className="notice__title">That did not work</p>
          <p style={{ marginBottom: 0 }}>{error}</p>
        </div>
      ) : sent ? (
        <div className="notice" role="status">
          <p className="notice__title">Another code is on its way</p>
          <p style={{ marginBottom: 0 }}>
            If it does not arrive, you can ask again in about {wait || 60} seconds.
          </p>
        </div>
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

      <form action={resendCodeAction}>
        <input type="hidden" name="phone" value={phone} />
        <button type="submit" className="btn btn--ghost">Send another code</button>
      </form>

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

import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Flash } from "@/components/Flash";
import { ApiError, type Me, getMe } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { startAssistedPaymentAction } from "./actions";

export const metadata: Metadata = { title: "Pay for an athlete" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/**
 * Assisted payment (CRD-04).
 *
 * A coordinator starts a checkout for an athlete who cannot pay online
 * themselves — the coordinator's own card is charged, but the ledger and the
 * receipt both land on the athlete named here, never on the coordinator.
 * Whether this specific pairing is allowed (the athlete's own LGA, ready to
 * be paid for, not already paid, within today's two caps) is entirely the
 * API's to decide; this screen only carries the KUID there.
 */
export default async function AssistPayPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let me: Me;
  try {
    me = await getMe(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }

  // Same rule as /review: an LGA coordinator's own LGA, or one a state
  // coordinator/admin names explicitly. Either way the API checks it again.
  const own = me.roles.find((r) => r.scope_kind === "lga")?.scope_id ?? "";
  const lga = one(params.lga) || own;
  const kuid = one(params.kuid);
  const error = one(params.error);

  if (!lga) {
    return (
      <div className="stack">
        <h1>Pay for an athlete</h1>
        <Flash variant="warn" title="No LGA to act in">
          <p style={{ marginBottom: 0 }}>
            This account is not an LGA coordinator. Assisted payment is done by
            the coordinator of the athlete&rsquo;s own LGA.
          </p>
        </Flash>
      </div>
    );
  }

  return (
    <div className="stack">
      <p className="eyebrow">Coordinator &middot; CRD-04</p>
      <h1>Pay for an athlete</h1>
      <p className="lede">
        For someone who cannot pay online themselves. Your card is charged; the
        badge and the receipt are theirs.
      </p>

      {error ? (
        <Flash variant="bad" title="That did not work">
          <p style={{ marginBottom: 0 }}>{error}</p>
        </Flash>
      ) : null}

      <form action={startAssistedPaymentAction} className="doc" noValidate>
        <div className="doc__body">
          <input type="hidden" name="lga" value={lga} />
          <div className={error ? "field field--error" : "field"}>
            <label htmlFor="kuid">Athlete&rsquo;s KAFRIADA ID</label>
            <span className="hint" id="kuid-hint">
              Must be an athlete in your own LGA who has already uploaded a
              photo and ID document.
            </span>
            <input
              id="kuid"
              name="kuid"
              required
              placeholder="KA-NG-JG-BKD-2026-000001"
              defaultValue={kuid}
              style={{ fontFamily: "var(--font-mono)" }}
              aria-describedby="kuid-hint"
            />
          </div>
          <button type="submit" className="btn btn--primary btn--block">
            Continue to payment
          </button>
        </div>
      </form>

      <p className="hint"><a href="/review">Back to review</a></p>
    </div>
  );
}

import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Flash } from "@/components/Flash";
import {
  ApiError,
  type CoordinatorDashboard,
  type Me,
  getCoordinatorDashboard,
  getMe,
  listLgas,
} from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";

export const metadata: Metadata = { title: "Coordinator" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/** Over this many hours a waiting case is amber; over the target, red. */
const AMBER_HOURS = 18;
const TARGET_HOURS = 24;

/**
 * The coordinator's home (CRD-01): what needs doing today in one LGA, on a phone.
 *
 * An LGA coordinator's LGA comes from their role; a state coordinator or an
 * administrator picks one. Every number is the API's, and everything here is a link, so
 * it works with JavaScript off.
 */
export default async function CoordinatorPage({ searchParams }: { searchParams: Promise<Search> }) {
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

  const own = me.roles.find((r) => r.scope_kind === "lga")?.scope_id ?? "";
  const canChoose = me.roles.some((r) => r.scope_kind === "state" || r.scope_kind === "global");
  const lga = one(params.lga) || own;

  if (!lga) {
    if (!canChoose) {
      return (
        <div className="stack">
          <h1>Coordinator</h1>
          <Flash variant="warn" title="No LGA to show">
            <p style={{ marginBottom: 0 }}>This account does not coordinate a local government area.</p>
          </Flash>
        </div>
      );
    }
    return <Chooser />;
  }

  let d: CoordinatorDashboard;
  try {
    d = await getCoordinatorDashboard(token, lga);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403 || error.status === 404) {
        return (
          <div className="stack">
            <h1>Coordinator</h1>
            <Flash variant="bad" title="You do not have access to this">
              <p style={{ marginBottom: 0 }}>You can only open your own local government area.</p>
            </Flash>
            {canChoose ? <Chooser /> : null}
          </div>
        );
      }
    }
    throw error;
  }

  const q = `lga=${encodeURIComponent(d.lga_id)}`;
  const hours = d.oldest_waiting_hours;

  return (
    <div className="stack">
      <p className="eyebrow">{d.lga_name} LGA &middot; {me.full_name}</p>
      <h1>Today</h1>

      <section className="doc" aria-label="The register">
        <div className="doc__body">
          <dl className="facts">
            <div className="fact"><dt>Registered</dt><dd>{d.registered}</dd></div>
            <div className="fact"><dt>Paid</dt><dd>{d.paid}</dd></div>
            <div className="fact"><dt>To review</dt><dd>{d.to_review}</dd></div>
            <div className="fact"><dt>Clubs</dt><dd>{d.clubs}</dd></div>
          </dl>
        </div>
      </section>

      {d.to_review === 0 ? (
        <Flash variant="good" title="Nothing is waiting">
          <p style={{ marginBottom: 0 }}>Every verification in this LGA has been decided.</p>
        </Flash>
      ) : (
        <Flash
          variant={hours !== null && hours >= TARGET_HOURS ? "bad" : hours !== null && hours >= AMBER_HOURS ? "warn" : "info"}
          title={`Oldest waiting ${hours === null || hours < 1 ? "under an hour" : `${hours}h`}`}
        >
          <p>
            {d.to_review === 1 ? "One verification needs" : `${d.to_review} verifications need`} a
            decision. The target is {TARGET_HOURS} hours.
          </p>
          <a href={`/review?${q}`} className="btn btn--primary">Review now</a>
        </Flash>
      )}

      <h2>What do you need to do?</h2>
      <div style={{ display: "flex", gap: "var(--s3)", flexWrap: "wrap" }}>
        <a href={`/review?${q}`} className="btn btn--ghost">Review verifications</a>
        <a href={`/coordinator/find?${q}`} className="btn btn--ghost">Find an athlete</a>
        <a href={`/coordinator/cards?${q}`} className="btn btn--ghost">Print QR cards</a>
        {d.can_assist && !d.cap_reached ? (
          <a href={`/assist-pay?${q}`} className="btn btn--ghost">Pay for an athlete</a>
        ) : null}
      </div>

      {d.can_assist ? (
        <section className="doc" aria-label="Cash collected today">
          <div className="doc__body">
            <p className="eyebrow">Cash collected today</p>
            <dl className="facts">
              <div className="fact">
                <dt>{d.collected_count} {d.collected_count === 1 ? "payment" : "payments"}</dt>
                <dd><span className="amount">{formatNaira(d.collected_kobo)}</span></dd>
              </div>
              <div className="fact">
                <dt>Daily limit</dt>
                <dd>{formatNaira(d.limit_kobo)} / {d.limit_count} payments</dd>
              </div>
            </dl>
            {d.cap_reached ? (
              <p className="hint" style={{ marginBottom: 0 }}>
                You have reached today&rsquo;s limit. Assisted payments start again tomorrow.
              </p>
            ) : null}
          </div>
        </section>
      ) : null}

      {canChoose ? <Chooser current={d.lga_id} /> : null}
    </div>
  );
}

async function Chooser({ current }: { current?: string }) {
  let options: Awaited<ReturnType<typeof listLgas>> = [];
  try {
    options = await listLgas();
  } catch {
    /* an unreachable list leaves an empty selector; the page still works for the LGA already chosen */
  }
  return (
    <form method="get" className="doc">
      <div className="doc__body">
        <div className="field">
          <label htmlFor="lga">Local government area</label>
          <select id="lga" name="lga" defaultValue={current ?? ""}>
            <option value="">Choose an area</option>
            {options.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
        </div>
        <button type="submit" className="btn btn--ghost btn--block">Show</button>
      </div>
    </form>
  );
}

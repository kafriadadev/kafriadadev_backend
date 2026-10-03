import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PageHead } from "@/components/PageHead";
import { Flash } from "@/components/Flash";
import { VerificationBadge } from "@/components/VerificationBadge";
import { ApiError, getMe, getProfile, type Me } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { signOutAction } from "./actions";

export const metadata: Metadata = { title: "My KAFRIADA" };
export const dynamic = "force-dynamic";

const ROLE_NAMES: Record<string, string> = {
  super_admin: "Administrator",
  state_coordinator: "State coordinator",
  lga_coordinator: "LGA coordinator",
  club_admin: "Club administrator",
  coach: "Coach",
  scout: "Scout",
  athlete: "Athlete",
};

/**
 * My KAFRIADA (ATH-01, first cut): who is signed in, their ID, and the way out.
 *
 * Everything is a link or a form, so it works with JavaScript off. The session
 * is checked by the API on every render; a stale cookie lands back on sign-in.
 */
export default async function MePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const welcome = Boolean((await searchParams).welcome);
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let me: Me;
  try {
    me = await getMe(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }

  const staffRoles = me.roles.filter((r) => r.role !== "athlete");
  const isAdmin = staffRoles.some((r) => r.role === "super_admin");
  const isCoordinator = staffRoles.some(
    (r) => r.role === "lga_coordinator" || r.role === "state_coordinator",
  );
  const clubs = me.roles.filter((r) => r.role === "club_admin" && r.scope_id);
  const hasWorkAreas = isAdmin || isCoordinator || clubs.length > 0;
  const kuid = me.kuid ? encodeURIComponent(me.kuid) : null;
  const verified = me.kuid
    ? Boolean((await getProfile(me.kuid).catch(() => null))?.is_verified)
    : false;

  return (
    <div className="page page--wide">
      <PageHead
        eyebrow="My account"
        title={me.full_name}
        app
        actions={
          <form action={signOutAction}>
            <button type="submit" className="btn btn--ghost">Sign out</button>
          </form>
        }
      />

      <div className="split">
        <div className="stack--lg">
          {welcome ? (
            <Flash variant="good" title="Your email is confirmed" autoDismissMs={6000}>
              <p className="mb0">Your account is open.</p>
            </Flash>
          ) : null}

          {kuid ? (
            <section aria-labelledby="athlete-h">
              <h2 className="section-title" id="athlete-h">My ID</h2>
              <div className="tiles">
                <a href={`/card/${kuid}`} className="tile tile--primary">
                  <span className="tile__title">My card</span>
                  <span className="tile__text">Print or download your ID card.</span>
                </a>
                <a href={`/a/${kuid}`} className="tile">
                  <span className="tile__title">Public profile</span>
                  <span className="tile__text">What a club or scout sees when they scan.</span>
                </a>
                {verified ? null : (
                  <a href="/verify" className="tile">
                    <span className="tile__title">Get verified</span>
                    <span className="tile__text">Add your photograph and the verified badge.</span>
                  </a>
                )}
                <a href="/details" className="tile">
                  <span className="tile__title">My details</span>
                  <span className="tile__text">Address, height, weight, emergency contact.</span>
                </a>
                <a href="/payments" className="tile">
                  <span className="tile__title">My payments</span>
                  <span className="tile__text">Every payment you have started.</span>
                </a>
              </div>
            </section>
          ) : null}

          {kuid ? (
            <section aria-labelledby="clubs-h">
              <h2 className="section-title" id="clubs-h">Clubs</h2>
              <div className="tiles">
                <a href="/clubs" className="tile">
                  <span className="tile__title">My clubs</span>
                  <span className="tile__text">Invitations and the club you play for.</span>
                </a>
                <a href="/clubs/new" className="tile">
                  <span className="tile__title">Register a club</span>
                  <span className="tile__text">Set up a club and add your players.</span>
                </a>
              </div>
            </section>
          ) : null}

          {hasWorkAreas ? (
            <section aria-labelledby="work-h">
              <h2 className="section-title" id="work-h">Work areas</h2>
              <div className="tiles">
                {isAdmin ? (
                  <a href="/admin" className="tile">
                    <span className="tile__title">Administrator console</span>
                    <span className="tile__text">Money, users, clubs and the audit log.</span>
                  </a>
                ) : null}
                {isCoordinator ? (
                  <a href="/coordinator" className="tile">
                    <span className="tile__title">Coordinator dashboard</span>
                    <span className="tile__text">Reviews, athletes and card printing.</span>
                  </a>
                ) : null}
                {clubs.map((r) => (
                  <a key={r.grant_id} href={`/clubs/${encodeURIComponent(r.scope_id as string)}`} className="tile">
                    <span className="tile__title">{r.scope_name ?? "My club"}</span>
                    <span className="tile__text">Roster, invitations and verification.</span>
                  </a>
                ))}
              </div>
            </section>
          ) : null}
        </div>

        <aside className="stack">
          <section className="doc" aria-label="Your account">
            <div className="doc__body">
              <p className="eyebrow">Account</p>
              <dl className="facts">
                {me.kuid ? (
                  <div className="fact">
                    <dt>KAFRIADA ID</dt>
                    <dd><span className="kuid">{me.kuid}</span></dd>
                  </div>
                ) : null}
                {me.kuid ? (
                  <div className="fact">
                    <dt>Status</dt>
                    <dd><VerificationBadge verified={verified} /></dd>
                  </div>
                ) : null}
                {me.lga_name ? (
                  <div className="fact">
                    <dt>LGA</dt>
                    <dd>{me.lga_name}</dd>
                  </div>
                ) : null}
                <div className="fact">
                  <dt>Phone</dt>
                  <dd>
                    {me.phone}
                  </dd>
                </div>
              </dl>
            </div>
          </section>

          {staffRoles.length ? (
            <div className="notice">
              <p className="notice__title">Your roles</p>
              <ul className="bullets mb-3">
                {staffRoles.map((r) => (
                  <li key={r.grant_id}>
                    {ROLE_NAMES[r.role] ?? r.role}
                    {r.scope_kind !== "global" ? ` — ${r.scope_name ?? r.scope_id}` : ""}
                  </li>
                ))}
              </ul>
              <p className="hint mb0">
                Staff are signed out after 30 minutes without activity, because
                phones are shared in the field.
              </p>
            </div>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

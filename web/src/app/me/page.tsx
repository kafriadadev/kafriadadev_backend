import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PageHead } from "@/components/PageHead";
import { Flash } from "@/components/Flash";
import { VerificationBadge } from "@/components/VerificationBadge";
import { ApiError, getMe, getProfile, type Me } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { signOutAction } from "./actions";

export const metadata: Metadata = { title: "My KAFRIADA NET" };
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
 * My KAFRIADA NET (ATH-01, first cut): who is signed in, their ID, and the way out.
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
    <div>
      <PageHead
        eyebrow="My account"
        title={me.full_name}
        app
        actions={
          <form action={signOutAction}>
            <button type="submit">Sign out</button>
          </form>
        }
      />

      <div>
        <div>
          {welcome ? (
            <Flash variant="good" title="Your email is confirmed" autoDismissMs={6000}>
              <p>Your account is open.</p>
            </Flash>
          ) : null}

          {kuid ? (
            <section aria-labelledby="athlete-h">
              <h2 id="athlete-h">My ID</h2>
              <div>
                <a href={`/card/${kuid}`}>
                  <span>My card</span>
                  <span>Print or download your ID card.</span>
                </a>
                <a href={`/a/${kuid}`}>
                  <span>Public profile</span>
                  <span>What a club or scout sees when they scan.</span>
                </a>
                {verified ? null : (
                  <a href="/verify">
                    <span>Get verified</span>
                    <span>Add your photograph and the verified badge.</span>
                  </a>
                )}
                <a href="/details">
                  <span>My details</span>
                  <span>Address, height, weight, emergency contact.</span>
                </a>
                <a href="/payments">
                  <span>My payments</span>
                  <span>Every payment you have started.</span>
                </a>
              </div>
            </section>
          ) : null}

          {kuid ? (
            <section aria-labelledby="clubs-h">
              <h2 id="clubs-h">Clubs</h2>
              <div>
                <a href="/clubs">
                  <span>My clubs</span>
                  <span>Invitations and the club you play for.</span>
                </a>
              </div>
            </section>
          ) : null}

          {hasWorkAreas ? (
            <section aria-labelledby="work-h">
              <h2 id="work-h">Work areas</h2>
              <div>
                {isAdmin ? (
                  <a href="/admin">
                    <span>Administrator console</span>
                    <span>Money, users, clubs and the audit log.</span>
                  </a>
                ) : null}
                {isCoordinator ? (
                  <a href="/coordinator">
                    <span>Coordinator dashboard</span>
                    <span>Reviews, athletes and card printing.</span>
                  </a>
                ) : null}
                {isAdmin || isCoordinator ? (
                  <a href="/clubs/new">
                    <span>Register a club for someone</span>
                    <span>For a club that cannot sign itself up.</span>
                  </a>
                ) : null}
                {clubs.map((r) => (
                  <a key={r.grant_id} href={`/clubs/${encodeURIComponent(r.scope_id as string)}`}>
                    <span>{r.scope_name ?? "My club"}</span>
                    <span>Roster, invitations and verification.</span>
                  </a>
                ))}
              </div>
            </section>
          ) : null}
        </div>

        <aside>
          <section aria-label="Your account">
            <div>
              <p>Account</p>
              <dl>
                {me.kuid ? (
                  <div>
                    <dt>KAFRIADA NET ID</dt>
                    <dd><span>{me.kuid}</span></dd>
                  </div>
                ) : null}
                {me.kuid ? (
                  <div>
                    <dt>Status</dt>
                    <dd><VerificationBadge verified={verified} /></dd>
                  </div>
                ) : null}
                {me.lga_name ? (
                  <div>
                    <dt>LGA</dt>
                    <dd>{me.lga_name}</dd>
                  </div>
                ) : null}
                <div>
                  <dt>Phone</dt>
                  <dd>
                    {me.phone}
                  </dd>
                </div>
              </dl>
            </div>
          </section>

          {staffRoles.length ? (
            <div>
              <p>Your roles</p>
              <ul>
                {staffRoles.map((r) => (
                  <li key={r.grant_id}>
                    {ROLE_NAMES[r.role] ?? r.role}
                    {r.scope_kind !== "global" ? ` — ${r.scope_name ?? r.scope_id}` : ""}
                  </li>
                ))}
              </ul>
              <p>
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

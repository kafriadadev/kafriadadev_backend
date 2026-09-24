import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ApiError, getMe, type Me } from "@/lib/api";
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
export default async function MePage() {
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

  return (
    <div className="stack">
      <p className="eyebrow">Signed in</p>
      <h1>{me.full_name}</h1>

      <section className="doc" aria-label="Your account">
        <div className="doc__body">
          <dl className="facts">
            {me.kuid ? (
              <div className="fact">
                <dt>KAFRIADA ID</dt>
                <dd><span className="kuid">{me.kuid}</span></dd>
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
              <dd>{me.phone}</dd>
            </div>
          </dl>
        </div>
      </section>

      {!me.phone_verified ? (
        <div className="notice notice--warn">
          <p className="notice__title">Confirm your phone number</p>
          <p style={{ marginBottom: "var(--s3)" }}>
            Your ID is already yours. Confirming the number is how we know the
            phone belongs to you, and it is needed before you can be verified.
          </p>
          <a href="/register/confirm">Enter the code</a>
        </div>
      ) : null}

      {me.kuid ? (
        <div style={{ display: "flex", gap: "var(--s3)", flexWrap: "wrap" }}>
          <a href={`/card/${encodeURIComponent(me.kuid)}`} className="btn btn--primary">
            My card
          </a>
          <a href={`/a/${encodeURIComponent(me.kuid)}`} className="btn btn--ghost">
            My public profile
          </a>
          {me.phone_verified ? (
            <a href="/verify" className="btn btn--ghost">Get verified</a>
          ) : null}
          <a href="/payments" className="btn btn--ghost">My payments</a>
          <a href="/details" className="btn btn--ghost">Edit my details</a>
          <a href="/clubs/new" className="btn btn--ghost">Register a club</a>
        </div>
      ) : null}

      {staffRoles.some((r) => r.role === "lga_coordinator" || r.role === "state_coordinator") ? (
        <p>
          <a href="/review" className="btn btn--ghost">Review verifications</a>
        </p>
      ) : null}

      {me.roles
        .filter((r) => r.role === "club_admin" && r.scope_id)
        .map((r) => (
          <p key={r.grant_id}>
            <a href={`/clubs/${encodeURIComponent(r.scope_id as string)}`} className="btn btn--ghost">
              {r.scope_name ?? "My club"}
            </a>
          </p>
        ))}

      {staffRoles.length ? (
        <div className="notice">
          <p className="notice__title">Your roles</p>
          <ul style={{ margin: "0 0 var(--s3)", paddingLeft: "1.1em" }}>
            {staffRoles.map((r) => (
              <li key={r.grant_id}>
                {ROLE_NAMES[r.role] ?? r.role}
                {r.scope_kind !== "global" ? ` — ${r.scope_name ?? r.scope_id}` : ""}
              </li>
            ))}
          </ul>
          <p style={{ marginBottom: 0 }}>
            Staff are signed out after 30 minutes without activity, because
            phones are shared in the field.
          </p>
        </div>
      ) : null}

      <form action={signOutAction}>
        <button type="submit" className="btn btn--ghost">Sign out</button>
      </form>
    </div>
  );
}

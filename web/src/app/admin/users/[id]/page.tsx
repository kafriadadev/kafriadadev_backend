import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { EmptyState } from "@/components/EmptyState";
import { PageHead } from "@/components/PageHead";
import { AdminShell } from "@/components/AdminNav";
import { Flash } from "@/components/Flash";
import { SubmitButton } from "@/components/SubmitButton";
import {
  type AdminUser,
  ApiError,
  getAdminUser,
  getRoleKinds,
  listLgas,
} from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { endSessionsAction, grantAction, revokeAction } from "./actions";

export const metadata: Metadata = { title: "User" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

const DONE: Record<string, string> = {
  granted: "The role was granted.",
  revoked: "The role was revoked.",
  sessions: "Every session this person held has ended.",
};

/**
 * One person (ADM-02): what they hold and where, grant a role, revoke one, end their
 * sessions. Role and scope are one action, never two, and granting or revoking asks for
 * the administrator's password again. The checks are the API's.
 */
export default async function UserPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Search>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let user: AdminUser;
  let kinds: Awaited<ReturnType<typeof getRoleKinds>>;
  let lgas: Awaited<ReturnType<typeof listLgas>> = [];
  try {
    [user, kinds] = await Promise.all([getAdminUser(token, id), getRoleKinds(token)]);
    lgas = await listLgas();
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403 || error.status === 404 || error.status === 422) {
        return (
          <AdminShell current="/admin/users">
            <PageHead eyebrow="Administrator" title="User" app />
            <Flash variant="bad" title="Not found or not allowed">
              <p>
                There is no such user, or you do not have access. <a href="/admin/users">Back to users</a>
              </p>
            </Flash>
          </AdminShell>
        );
      }
    }
    throw error;
  }

  const error = one(query.error);
  const done = DONE[one(query.done)];
  const scopeLabel: Record<string, string> = {
    global: "not tied to a place",
    state: "one state",
    lga: "one LGA",
    club: "one club",
  };

  return (
    <AdminShell current="/admin/users">
      <PageHead
        back={{ href: "/admin/users", label: "Users and roles" }}
        eyebrow="User"
        title={user.full_name}
        lede={
          <>
            {user.phone_masked}
            {user.kuid ? <> &middot; <span>{user.kuid}</span></> : null}
          </>
        }
        app
      />

      {error ? (
        <Flash variant="bad" title="That did not work">
          <p>{error}</p>
        </Flash>
      ) : null}
      {done ? (
        <Flash variant="good" title="Done">
          <p>{done}</p>
        </Flash>
      ) : null}

      <div>
      <div>
      <h2>Roles</h2>
      {user.roles.length === 0 ? <EmptyState title="This person holds no roles" /> : null}
      {user.roles.map((r) => (
        <section key={r.grant_id} aria-label={r.role}>
          <div>
            <p>
              {r.role}
              {r.scope_name ? ` — ${r.scope_name}` : r.scope_kind === "global" ? "" : ` — ${r.scope_id}`}
            </p>
            <details>
            <summary>Revoke this role</summary>
            <form action={revokeAction}>
              <input type="hidden" name="user" value={user.user_id} />
              <input type="hidden" name="grant" value={r.grant_id} />
              <div>
                <label htmlFor={`reason-${r.grant_id}`}>Reason for revoking</label>
                <input id={`reason-${r.grant_id}`} name="reason" required maxLength={300} />
              </div>
              <div>
                <label htmlFor={`pw-${r.grant_id}`}>Your password</label>
                <input id={`pw-${r.grant_id}`} name="current_password" type="password" required autoComplete="current-password" />
              </div>
              <SubmitButton pending="Revoking…">Revoke this role</SubmitButton>
            </form>
            </details>
          </div>
        </section>
      ))}

      <h2>Sessions</h2>
      <form action={endSessionsAction}>
        <div>
          <input type="hidden" name="user" value={user.user_id} />
          <div>
            <label htmlFor="end-reason">Reason for ending every session</label>
            <input id="end-reason" name="reason" required maxLength={300} />
          </div>
          <SubmitButton pending="Ending sessions…">End all sessions</SubmitButton>
        </div>
      </form>

      </div>

      <aside>
      <h2>Grant a role</h2>
      <form action={grantAction}>
        <div>
          <input type="hidden" name="user" value={user.user_id} />
          <div>
            <label htmlFor="role">Role</label>
            <select id="role" name="role" required defaultValue="">
              <option value="">Choose a role</option>
              {kinds.map((k) => (
                <option key={k.code} value={k.code}>
                  {k.code} — {scopeLabel[k.scope_kind] ?? k.scope_kind}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="scope_id">Where it applies</label>
            <span>
              Required for every role except those not tied to a place. A role that needs a place
              cannot be granted without one.
            </span>
            <select id="scope_id" name="scope_id" defaultValue="">
              <option value="">Not tied to a place</option>
              <optgroup label="State">
                <option value="NG-JG">Jigawa</option>
              </optgroup>
              <optgroup label="Local government area">
                {lgas.map((l) => (
                  <option key={l.id} value={l.id}>{l.name}</option>
                ))}
              </optgroup>
            </select>
          </div>
          <div>
            <label htmlFor="club_id">Or a club&rsquo;s id</label>
            <input id="club_id" name="club_id" autoComplete="off" />
          </div>
          <div>
            <label htmlFor="reason">Reason</label>
            <input id="reason" name="reason" required maxLength={300} />
          </div>
          <div>
            <label htmlFor="current_password">Your password</label>
            <input id="current_password" name="current_password" type="password" required autoComplete="current-password" />
            <span>You are asked for your password again before this is saved.</span>
          </div>
          <SubmitButton pending="Granting…">Grant role</SubmitButton>
        </div>
      </form>

      </aside>
      </div>
    </AdminShell>
  );
}

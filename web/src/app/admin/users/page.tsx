import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AdminNav } from "@/components/AdminNav";
import { Flash } from "@/components/Flash";
import { type AdminUsers, ApiError, findAdminUsers, getRoleKinds } from "@/lib/api";
import { sessionToken } from "@/lib/session";

export const metadata: Metadata = { title: "Users and roles" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

const seen = (iso: string | null): string =>
  iso
    ? new Date(iso).toLocaleString("en-GB", {
        day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lagos",
      })
    : "Never";

/** Users and roles (ADM-02): find a person, see exactly what they hold and where. */
export default async function UsersPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  const q = one(params.q).trim();
  const role = one(params.role);
  const page = Math.max(Number.parseInt(one(params.page) || "1", 10) || 1, 1);

  let result: AdminUsers;
  let roles: Awaited<ReturnType<typeof getRoleKinds>>;
  try {
    [result, roles] = await Promise.all([findAdminUsers(token, q, role, page), getRoleKinds(token)]);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403) {
        return (
          <div className="stack">
            <h1>Users and roles</h1>
            <Flash variant="bad" title="You do not have access to this">
              <p style={{ marginBottom: 0 }}>Only a super administrator can open this.</p>
            </Flash>
          </div>
        );
      }
    }
    throw error;
  }

  const link = (p: number) => `/admin/users?${new URLSearchParams({ q, role, page: String(p) })}`;

  return (
    <div className="stack">
      <AdminNav current="/admin/users" />
      <h1>Users and roles</h1>

      <form method="get" className="doc">
        <div className="doc__body">
          <div className="field">
            <label htmlFor="q">Name, phone or KAFRIADA ID</label>
            <input id="q" name="q" defaultValue={q} />
          </div>
          <div className="field">
            <label htmlFor="role">Role</label>
            <select id="role" name="role" defaultValue={role}>
              <option value="">All roles</option>
              {roles.map((r) => (
                <option key={r.code} value={r.code}>{r.code}</option>
              ))}
            </select>
          </div>
          <button type="submit" className="btn btn--primary btn--block">Search</button>
        </div>
      </form>

      {result.users.length === 0 ? <p className="hint">No one matches.</p> : null}

      {result.users.map((u) => (
        <section className="doc" key={u.user_id} aria-label={u.full_name}>
          <div className="doc__body">
            <p style={{ fontWeight: 700, marginBottom: "var(--s2)" }}>
              <a href={`/admin/users/${u.user_id}`}>{u.full_name}</a>
            </p>
            <p style={{ marginBottom: "var(--s2)" }}>
              {u.phone_masked}
              {u.kuid ? <> &middot; <span className="kuid">{u.kuid}</span></> : null}
            </p>
            <p className="hint" style={{ marginBottom: "var(--s2)" }}>Last seen {seen(u.last_seen)}</p>
            <p style={{ marginBottom: 0 }}>
              {u.roles.length
                ? u.roles.map((r) => `${r.role}${r.scope_name ? ` — ${r.scope_name}` : ""}`).join(", ")
                : "No roles"}
            </p>
          </div>
        </section>
      ))}

      {page > 1 || result.has_more ? (
        <nav aria-label="Pages" style={{ display: "flex", gap: "var(--s4)" }}>
          {page > 1 ? <a href={link(page - 1)}>Previous</a> : null}
          {result.has_more ? <a href={link(page + 1)}>Next</a> : null}
        </nav>
      ) : null}
    </div>
  );
}

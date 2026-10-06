import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { NoAccess } from "@/components/NoAccess";
import { AdminShell } from "@/components/AdminNav";
import { EmptyState } from "@/components/EmptyState";
import { PageHead } from "@/components/PageHead";
import { Pager } from "@/components/Pager";
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
          <NoAccess title="Users and roles" />
        );
      }
    }
    throw error;
  }

  const link = (p: number) => `/admin/users?${new URLSearchParams({ q, role, page: String(p) })}`;

  return (
    <AdminShell current="/admin/users">
      <PageHead eyebrow="Administrator" title="Users and roles" app />

      <form method="get" role="search">
        <div>
          <label htmlFor="q">Name, phone or KAFRIADA NET ID</label>
          <input id="q" name="q" defaultValue={q} />
        </div>
        <div>
          <label htmlFor="role">Role</label>
          <select id="role" name="role" defaultValue={role}>
            <option value="">All roles</option>
            {roles.map((r) => (
              <option key={r.code} value={r.code}>{r.code}</option>
            ))}
          </select>
        </div>
        <button type="submit">Search</button>
      </form>

      {result.users.length === 0 ? (
        <EmptyState title="No one matches">
          <p>Try part of a name, the last digits of a phone number, or a full ID.</p>
        </EmptyState>
      ) : (
        <div>
          <table>
            <thead>
              <tr><th>Name</th><th>Phone</th><th>KAFRIADA NET ID</th><th>Roles</th><th>Last seen</th></tr>
            </thead>
            <tbody>
              {result.users.map((u) => (
                <tr key={u.user_id}>
                  <td data-label=""><a href={`/admin/users/${u.user_id}`}><strong>{u.full_name}</strong></a></td>
                  <td data-label="Phone"><span>{u.phone_masked}</span></td>
                  <td data-label="ID">{u.kuid ? <span>{u.kuid}</span> : <span>None</span>}</td>
                  <td data-label="Roles">
                    <span>
                      {u.roles.length
                        ? u.roles.map((r) => `${r.role}${r.scope_name ? ` — ${r.scope_name}` : ""}`).join(", ")
                        : "No roles"}
                    </span>
                  </td>
                  <td data-label="Last seen"><span>{seen(u.last_seen)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Pager page={page} prev={page > 1 ? link(page - 1) : null} next={result.has_more ? link(page + 1) : null} />
    </AdminShell>
  );
}

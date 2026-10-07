import type { Metadata } from "next";
import { WithKuids } from "@/components/ui/Kuid";
import { redirect } from "next/navigation";

import { NoAccess } from "@/components/NoAccess";
import { AdminShell } from "@/components/AdminNav";
import { EmptyState } from "@/components/EmptyState";
import { PageHead } from "@/components/PageHead";
import { Pager } from "@/components/Pager";
import { Flash } from "@/components/Flash";
import { ApiError, type AuditPage, getAuditLog } from "@/lib/api";
import { sessionToken } from "@/lib/session";

export const metadata: Metadata = { title: "Audit log" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

const when = (iso: string): string =>
  new Date(iso).toLocaleString("en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Africa/Lagos",
  });

/**
 * The audit log (ADM-06): who did what, and when, without a developer or a database
 * console. It has no edit and no delete because the database has no such grant — this
 * screen could not offer them if it wanted to.
 */
export default async function AuditLogPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  const filters = {
    actor: one(params.actor).trim(),
    action: one(params.action).trim(),
    since: one(params.since),
    until: one(params.until),
    page: Math.max(Number.parseInt(one(params.page) || "1", 10) || 1, 1),
  };

  let log: AuditPage | null = null;
  let problem = "";
  try {
    log = await getAuditLog(token, filters);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403) {
        return (
          <NoAccess title="Audit log" />
        );
      }
      if (error.status === 422) problem = "Check the dates: use the form year-month-day.";
      else throw error;
    } else throw error;
  }

  const link = (p: number) =>
    `/admin/audit?${new URLSearchParams({
      actor: filters.actor, action: filters.action, since: filters.since, until: filters.until, page: String(p),
    })}`;

  return (
    <AdminShell current="/admin/audit">
      <PageHead eyebrow="Administrator" title="Audit log" app />

      <form method="get" role="search">
        <div>
          <label htmlFor="actor">Who</label>
          <input id="actor" name="actor" defaultValue={filters.actor} />
        </div>
        <div>
          <label htmlFor="action">Action</label>
          <input id="action" name="action" defaultValue={filters.action} placeholder="verification.approved" />
        </div>
        <div>
          <label htmlFor="since">From</label>
          <input id="since" name="since" type="date" defaultValue={filters.since} />
        </div>
        <div>
          <label htmlFor="until">To</label>
          <input id="until" name="until" type="date" defaultValue={filters.until} />
        </div>
        <button type="submit">Filter</button>
      </form>

      {problem ? (
        <Flash variant="bad" title="That did not work">
          <p>{problem}</p>
        </Flash>
      ) : null}

      {log && log.entries.length === 0 ? <EmptyState title="No entries match" /> : null}

      {log && log.entries.length > 0 ? (
        <div>
          <table>
            <thead>
              <tr><th>When</th><th>Action</th><th>Who</th><th>Subject</th></tr>
            </thead>
            <tbody>
              {log.entries.map((e) => (
                <tr key={e.entry_id}>
                  <td data-label="When"><span>{when(e.occurred_at)}</span></td>
                  <td data-label="Action"><span>{e.action}</span></td>
                  <td data-label="Who">
                    <span>{e.actor}{e.actor_role ? ` (${e.actor_role})` : ""}</span>
                  </td>
                  <td data-label="Subject">
                    <span>
                      {e.subject_type} <WithKuids text={String(e.subject_id ?? "")} />
                      {e.reference ? ` · ref ${e.reference}` : ""}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {log ? (
        <Pager
          page={filters.page}
          prev={filters.page > 1 ? link(filters.page - 1) : null}
          next={log.has_more ? link(filters.page + 1) : null}
        />
      ) : null}

      <p>
        Audit records cannot be edited or deleted by anyone, including administrators.
      </p>
    </AdminShell>
  );
}

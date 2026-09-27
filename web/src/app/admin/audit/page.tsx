import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AdminNav } from "@/components/AdminNav";
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
          <div className="stack">
            <h1>Audit log</h1>
            <Flash variant="bad" title="You do not have access to this">
              <p style={{ marginBottom: 0 }}>Only a super administrator can open this.</p>
            </Flash>
          </div>
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
    <div className="stack">
      <AdminNav current="/admin/audit" />
      <h1>Audit log</h1>

      <form method="get" className="doc">
        <div className="doc__body">
          <div className="field">
            <label htmlFor="actor">Who</label>
            <input id="actor" name="actor" defaultValue={filters.actor} />
          </div>
          <div className="field">
            <label htmlFor="action">Action</label>
            <input id="action" name="action" defaultValue={filters.action} placeholder="verification.approved" />
          </div>
          <div className="field">
            <label htmlFor="since">From</label>
            <input id="since" name="since" type="date" defaultValue={filters.since} />
          </div>
          <div className="field">
            <label htmlFor="until">To</label>
            <input id="until" name="until" type="date" defaultValue={filters.until} />
          </div>
          <button type="submit" className="btn btn--primary btn--block">Filter</button>
        </div>
      </form>

      {problem ? (
        <Flash variant="bad" title="That did not work">
          <p style={{ marginBottom: 0 }}>{problem}</p>
        </Flash>
      ) : null}

      {log && log.entries.length === 0 ? <p className="hint">No entries match.</p> : null}

      {log?.entries.map((e) => (
        <section className="doc" key={e.entry_id} aria-label={e.action}>
          <div className="doc__body">
            <p style={{ fontWeight: 700, marginBottom: "var(--s2)", overflowWrap: "anywhere" }}>{e.action}</p>
            <p style={{ marginBottom: "var(--s2)" }}>
              {e.actor}
              {e.actor_role ? ` (${e.actor_role})` : ""} &middot; {when(e.occurred_at)}
            </p>
            <p className="hint" style={{ marginBottom: 0, overflowWrap: "anywhere" }}>
              {e.subject_type} {e.subject_id}
              {e.reference ? ` · ref ${e.reference}` : ""}
            </p>
          </div>
        </section>
      ))}

      {log && (filters.page > 1 || log.has_more) ? (
        <nav aria-label="Pages" style={{ display: "flex", gap: "var(--s4)" }}>
          {filters.page > 1 ? <a href={link(filters.page - 1)}>Previous</a> : null}
          {log.has_more ? <a href={link(filters.page + 1)}>Next</a> : null}
        </nav>
      ) : null}

      <p className="hint">
        Audit records cannot be edited or deleted by anyone, including administrators.
      </p>
    </div>
  );
}

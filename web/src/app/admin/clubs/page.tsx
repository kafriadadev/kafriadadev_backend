import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Badge, type BadgeTone, Segmented } from "@/components/console";
import { NoAccess } from "@/components/NoAccess";
import { buttonClass } from "@/components/ui/Button";
import { AdminShell } from "@/components/AdminNav";
import { EmptyState } from "@/components/EmptyState";
import { PageHead } from "@/components/PageHead";
import { Pager } from "@/components/Pager";
import { Flash } from "@/components/Flash";
import { SubmitButton } from "@/components/SubmitButton";
import { type AdminClubs, ApiError, listAdminClubs } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { clubStatusAction } from "./actions";

export const metadata: Metadata = { title: "Clubs" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

const FILTERS = [
  { key: "", label: "All" },
  { key: "pending_review", label: "Waiting for approval" },
  { key: "approved", label: "Approved" },
  { key: "suspended", label: "Suspended" },
] as const;

const TONE: Record<string, BadgeTone> = { pending_review: "warn", approved: "good", suspended: "bad" };

const STATUS_LABEL: Record<string, string> = {
  pending_review: "Waiting for approval",
  approved: "Approved",
  suspended: "Suspended",
};

/** Clubs, those waiting for approval first: approve one so it can build a roster, or suspend it. */
export default async function AdminClubsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  const status = one(params.status);
  const page = Math.max(Number.parseInt(one(params.page) || "1", 10) || 1, 1);

  let result: AdminClubs;
  try {
    result = await listAdminClubs(token, status, page);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403) {
        return (
          <NoAccess title="Clubs" />
        );
      }
    }
    throw error;
  }

  const done = one(params.done);
  const error = one(params.error);
  const link = (p: number) => `/admin/clubs?${new URLSearchParams({ status, page: String(p) })}`;

  return (
    <AdminShell current="/admin/clubs">
      <PageHead title="Clubs" lede="Approve a club so it can build a squad, or suspend one that should not be inviting players." />

      {done ? (
        <Flash
          variant="good"
          title={done === "approved" ? "Club approved" : done === "revoked" ? "Verification withdrawn" : "Club suspended"}
        >
          <p>
            {done === "approved"
              ? "The club can now build a roster."
              : done === "revoked"
                ? "The club has been told, and can be verified again from scratch."
                : "The club can no longer invite players."}
          </p>
        </Flash>
      ) : null}
      {error ? (
        <Flash variant="bad" title="That did not work">
          <p>{error}</p>
        </Flash>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented
          label="Filter clubs"
          current={`/admin/clubs${status ? `?status=${status}` : ""}`}
          items={FILTERS.map((f) => ({ href: `/admin/clubs${f.key ? `?status=${f.key}` : ""}`, label: f.label }))}
        />
      </div>

      {result.clubs.length === 0 ? (
        <EmptyState title="No clubs here" />
      ) : (
        <table>
          <caption className="sr-only">Clubs, those waiting for approval first</caption>
          <thead>
            <tr><th scope="col">Club</th><th scope="col">LGA</th><th scope="col">Representative</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Actions</span></th></tr>
          </thead>
          <tbody>
            {result.clubs.map((c) => (
              <tr key={c.club_id}>
                <td data-label="">
                  <a href={`/clubs/${c.club_id}`} className="font-bold">{c.name}</a>
                  <span className="block text-xs text-muted">{c.sport}</span>
                </td>
                <td data-label="LGA">{c.lga_name}</td>
                <td data-label="Representative">{c.representative}</td>
                <td data-label="Status">
                  <span className="inline-flex flex-wrap gap-1.5">
                    <Badge tone={TONE[c.status] ?? "neutral"}>{STATUS_LABEL[c.status] ?? c.status}</Badge>
                    {c.verified ? <Badge tone="info">Verified</Badge> : null}
                  </span>
                </td>
                <td data-label="">
                  <div className="flex flex-wrap justify-end gap-2">
                    {c.status !== "approved" ? (
                      <form action={clubStatusAction} className="contents">
                        <input type="hidden" name="club" value={c.club_id} />
                        <input type="hidden" name="status" value={status} />
                        <input type="hidden" name="change" value="approve" />
                        <SubmitButton pending="Approving…">Approve</SubmitButton>
                      </form>
                    ) : null}
                    {c.status !== "suspended" ? (
                      <form action={clubStatusAction} className="contents">
                        <input type="hidden" name="club" value={c.club_id} />
                        <input type="hidden" name="status" value={status} />
                        <input type="hidden" name="change" value="suspend" />
                        <SubmitButton variant="quietDanger" pending="Suspending…">Suspend</SubmitButton>
                      </form>
                    ) : null}
                    {c.verified ? (
                      <a href={`/admin/clubs/${c.club_id}/revoke`} className={buttonClass({ variant: "secondary", size: "sm" })}>Withdraw verification</a>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Pager page={page} prev={page > 1 ? link(page - 1) : null} next={result.has_more ? link(page + 1) : null} />
    </AdminShell>
  );
}

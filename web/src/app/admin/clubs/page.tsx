import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { NoAccess } from "@/components/NoAccess";
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
      <PageHead eyebrow="Administrator" title="Clubs" app />

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

      <nav aria-label="Filter">
        {FILTERS.map((f) =>
          f.key === status ? (
            <strong key={f.key} aria-current="page">{f.label}</strong>
          ) : (
            <a key={f.key} href={`/admin/clubs${f.key ? `?status=${f.key}` : ""}`}>{f.label}</a>
          ),
        )}
      </nav>

      {result.clubs.length === 0 ? (
        <EmptyState title="No clubs here" />
      ) : (
        <ul>
          {result.clubs.map((c) => (
            <li key={c.club_id}>
              <div>
                <p>
                  <a href={`/clubs/${c.club_id}`}>{c.name}</a>{" "}
                  <span>
                    {STATUS_LABEL[c.status] ?? c.status}
                  </span>{" "}
                  {c.verified ? <span>Verified</span> : null}
                </p>
                <p>
                  {c.sport} &middot; {c.lga_name} &middot; run by {c.representative}
                </p>
              </div>
              <div>
                {c.status !== "approved" ? (
                  <form action={clubStatusAction}>
                    <input type="hidden" name="club" value={c.club_id} />
                    <input type="hidden" name="status" value={status} />
                    <input type="hidden" name="change" value="approve" />
                    <SubmitButton pending="Approving…">Approve</SubmitButton>
                  </form>
                ) : null}
                {c.status !== "suspended" ? (
                  <form action={clubStatusAction}>
                    <input type="hidden" name="club" value={c.club_id} />
                    <input type="hidden" name="status" value={status} />
                    <input type="hidden" name="change" value="suspend" />
                    <SubmitButton pending="Suspending…">Suspend</SubmitButton>
                  </form>
                ) : null}
                {c.verified ? (
                  <a href={`/admin/clubs/${c.club_id}/revoke`}>Withdraw verification</a>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      <Pager page={page} prev={page > 1 ? link(page - 1) : null} next={result.has_more ? link(page + 1) : null} />
    </AdminShell>
  );
}

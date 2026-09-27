import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AdminNav } from "@/components/AdminNav";
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
          <div className="stack">
            <h1>Clubs</h1>
            <Flash variant="bad" title="You do not have access to this">
              <p style={{ marginBottom: 0 }}>Only a super administrator can open this.</p>
            </Flash>
          </div>
        );
      }
    }
    throw error;
  }

  const done = one(params.done);
  const error = one(params.error);
  const link = (p: number) => `/admin/clubs?${new URLSearchParams({ status, page: String(p) })}`;

  return (
    <div className="stack">
      <AdminNav current="/admin/clubs" />
      <h1>Clubs</h1>

      {done ? (
        <Flash
          variant="good"
          title={done === "approved" ? "Club approved" : done === "revoked" ? "Verification withdrawn" : "Club suspended"}
        >
          <p style={{ marginBottom: 0 }}>
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
          <p style={{ marginBottom: 0 }}>{error}</p>
        </Flash>
      ) : null}

      <nav aria-label="Filter" style={{ display: "flex", gap: "var(--s4)", flexWrap: "wrap" }}>
        {FILTERS.map((f) =>
          f.key === status ? (
            <strong key={f.key} aria-current="page">{f.label}</strong>
          ) : (
            <a key={f.key} href={`/admin/clubs${f.key ? `?status=${f.key}` : ""}`}>{f.label}</a>
          ),
        )}
      </nav>

      {result.clubs.length === 0 ? <p className="hint">No clubs.</p> : null}

      {result.clubs.map((c) => (
        <section className="doc" key={c.club_id} aria-label={c.name}>
          <div className="doc__body">
            <p style={{ fontWeight: 700, marginBottom: "var(--s2)" }}>{c.name}</p>
            <p style={{ marginBottom: "var(--s2)" }}>
              <span className={c.status === "approved" ? "pill pill--issued" : "pill pill--pending"}>
                {STATUS_LABEL[c.status] ?? c.status}
              </span>{" "}
              {c.verified ? <span className="pill pill--issued">Verified</span> : null}
            </p>
            <p className="hint" style={{ marginBottom: "var(--s3)" }}>
              {c.sport} &middot; {c.lga_name} &middot; run by {c.representative}
            </p>
            <div style={{ display: "flex", gap: "var(--s3)", flexWrap: "wrap" }}>
              {c.status !== "approved" ? (
                <form action={clubStatusAction}>
                  <input type="hidden" name="club" value={c.club_id} />
                  <input type="hidden" name="status" value={status} />
                  <input type="hidden" name="change" value="approve" />
                  <SubmitButton className="btn btn--primary" pending="Approving…">Approve</SubmitButton>
                </form>
              ) : null}
              {c.status !== "suspended" ? (
                <form action={clubStatusAction}>
                  <input type="hidden" name="club" value={c.club_id} />
                  <input type="hidden" name="status" value={status} />
                  <input type="hidden" name="change" value="suspend" />
                  <SubmitButton className="btn btn--ghost" pending="Suspending…">Suspend</SubmitButton>
                </form>
              ) : null}
              <a href={`/clubs/${c.club_id}`} className="btn btn--ghost">Open</a>
              {c.verified ? (
                <a href={`/admin/clubs/${c.club_id}/revoke`} className="btn btn--ghost">Withdraw verification</a>
              ) : null}
            </div>
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

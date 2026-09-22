import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Flash } from "@/components/Flash";
import {
  ApiError,
  type AdminVerificationLookup,
  findVerificationByKuid,
  getMe,
} from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { revokeAction } from "./actions";

export const metadata: Metadata = { title: "Withdraw a verification" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

const STATUS_LABEL: Record<string, string> = {
  draft: "Draft — not yet submitted",
  under_review: "Under review",
  approved: "Approved",
  rejected: "Rejected",
  escalated: "Escalated to the coordinator",
  revoked: "Already withdrawn",
};

/**
 * Withdraw a verification (ADM-03).
 *
 * The API (`POST /v1/admin/verification/{id}/revoke`) has existed since 2.2;
 * nothing let a super_admin get from a KUID to that request id. This is a
 * plain two-step form — look up, then confirm — because that gap, not the
 * revoke action itself, was the missing piece.
 */
export default async function RevokePage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let me;
  try {
    me = await getMe(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }
  if (!me.roles.some((r) => r.role === "super_admin")) {
    return (
      <div className="stack">
        <h1>Withdraw a verification</h1>
        <Flash variant="bad" title="You do not have access to this">
          <p style={{ marginBottom: 0 }}>Only a super administrator can withdraw a badge.</p>
        </Flash>
      </div>
    );
  }

  const kuid = one(params.kuid).trim();
  const error = one(params.error);
  const done = one(params.done);

  let found: AdminVerificationLookup | null = null;
  let lookupError: string | null = null;
  if (kuid && !done) {
    try {
      found = await findVerificationByKuid(token, kuid);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        lookupError = "No verification request is on file for that KAFRIADA ID.";
      } else if (caught instanceof ApiError) {
        lookupError = caught.message;
      } else {
        throw caught;
      }
    }
  }

  return (
    <div className="stack">
      <p className="eyebrow">Admin &middot; ADM-03</p>
      <h1>Withdraw a verification</h1>
      <p className="lede">
        Finds an athlete&rsquo;s verification by their KAFRIADA ID, so it can be
        withdrawn with a reason. The badge and photo come down immediately;
        the KAFRIADA ID itself is never affected.
      </p>

      {done ? (
        <Flash variant="good" title="Withdrawn">
          <p style={{ marginBottom: 0 }}>
            The badge for <span className="kuid">{done}</span> has been withdrawn.
            The athlete has been told by SMS, and the reason is kept permanently.
          </p>
        </Flash>
      ) : null}

      {error ? (
        <Flash variant="bad" title="That did not work">
          <p style={{ marginBottom: 0 }}>{error}</p>
        </Flash>
      ) : null}

      <form method="GET" className="doc" noValidate>
        <div className="doc__body">
          <div className="field">
            <label htmlFor="kuid">KAFRIADA ID</label>
            <input
              id="kuid"
              name="kuid"
              required
              placeholder="KA-NG-JG-BKD-2026-000001"
              defaultValue={kuid}
              style={{ fontFamily: "var(--font-mono)" }}
            />
          </div>
          <button type="submit" className="btn btn--primary btn--block">Find</button>
        </div>
      </form>

      {lookupError ? (
        <Flash variant="warn" title="Not found">
          <p style={{ marginBottom: 0 }}>{lookupError}</p>
        </Flash>
      ) : null}

      {found ? (
        <section className="doc" aria-label="What was found">
          <div className="doc__body">
            <dl className="facts">
              <div className="fact"><dt>Name</dt><dd>{found.full_name}</dd></div>
              <div className="fact"><dt>KAFRIADA ID</dt><dd><span className="kuid">{found.kuid}</span></dd></div>
              <div className="fact">
                <dt>Status</dt>
                <dd>{STATUS_LABEL[found.status] ?? found.status}</dd>
              </div>
            </dl>

            {found.revocable ? (
              <form action={revokeAction} style={{ marginTop: "var(--s5)" }}>
                <input type="hidden" name="request_id" value={found.request_id} />
                <input type="hidden" name="kuid" value={found.kuid} />
                <div className="field">
                  <label htmlFor="reason">Reason</label>
                  <span className="hint">Kept permanently. This is not shown to the athlete verbatim, unlike a rejection.</span>
                  <textarea id="reason" name="reason" maxLength={1000} required />
                </div>
                <div className="field">
                  <label htmlFor="current_password">Your password</label>
                  <span className="hint">Confirms this is really you, same as any other admin action.</span>
                  <input
                    id="current_password"
                    name="current_password"
                    type="password"
                    autoComplete="current-password"
                    required
                  />
                </div>
                <button type="submit" className="btn btn--primary btn--block">
                  Withdraw this verification
                </button>
              </form>
            ) : (
              <p className="hint" style={{ marginTop: "var(--s4)", marginBottom: 0 }}>
                Nothing to withdraw — only an approved verification can be.
              </p>
            )}
          </div>
        </section>
      ) : null}
    </div>
  );
}

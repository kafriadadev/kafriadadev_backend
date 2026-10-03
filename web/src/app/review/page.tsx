import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { CoordinatorNav } from "@/components/CoordinatorNav";
import { EmptyState } from "@/components/EmptyState";
import { PageHead } from "@/components/PageHead";
import {
  ApiError,
  getMe,
  getReviewCase,
  getReviewQueue,
  type Me,
  type QueueItem,
  type ReviewCase,
} from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";
import { decideAction } from "./actions";

export const metadata: Metadata = { title: "Review" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

const stamp = (iso: string | null): string =>
  iso
    ? new Date(iso).toLocaleString("en-GB", {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Africa/Lagos",
      })
    : "";

/** "Waiting 19h" — how long the oldest case has sat. */
function waiting(iso: string): string {
  const hours = Math.floor((Date.now() - new Date(iso).getTime()) / 3_600_000);
  return hours < 1 ? "under an hour" : hours < 48 ? `${hours}h` : `${Math.floor(hours / 24)} days`;
}

/**
 * Review queue and decision (CRD-02).
 *
 * Deliberately plain: one case at a time, everything needed on one screen, a list
 * and two buttons. It shows only what the API hands a reviewer — their own LGA, the
 * safe copies of the files, never their own record — and the buttons are plain form
 * posts. Whether a decision is allowed is the API's to say, not this page's.
 */
export default async function ReviewPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let me: Me;
  try {
    me = await getMe(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }

  // An LGA coordinator's LGA comes from their role; a state coordinator or an
  // administrator names one with ?lga=. Either way the API checks it.
  const own = me.roles.find((r) => r.scope_kind === "lga")?.scope_id ?? "";
  const lga = one(params.lga) || own;
  if (!lga) {
    return (
      <div className="page stack">
        <h1>Review</h1>
        <div className="notice notice--warn" role="status">
          <p className="notice__title">No LGA to review</p>
          <p className="mb0">
            This account is not an LGA coordinator. Reviews are done by the coordinator of the
            athlete&rsquo;s LGA.
          </p>
        </div>
      </div>
    );
  }

  let queue: QueueItem[];
  try {
    queue = await getReviewQueue(token, lga);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    if (error instanceof ApiError && error.status === 403) {
      return (
        <div className="page stack">
          <h1>Review</h1>
          <div className="notice notice--bad" role="alert">
            <p className="notice__title">You do not have access to this</p>
            <p className="mb0">You can only review athletes in your own LGA.</p>
          </div>
        </div>
      );
    }
    throw error;
  }

  const error = one(params.error);
  const done = one(params.done);
  const index = Math.max(Number.parseInt(one(params.n) || "0", 10) || 0, 0);
  const current = queue[index];

  let detail: ReviewCase | null = null;
  if (current) {
    try {
      detail = await getReviewCase(token, lga, current.request_id);
    } catch (caught) {
      if (!(caught instanceof ApiError) || caught.status !== 404) throw caught;
    }
  }

  const banner = error ? (
    <div className="notice notice--bad" role="alert" tabIndex={-1}>
      <p className="notice__title">That did not work</p>
      <p className="mb0">{error}</p>
    </div>
  ) : done ? (
    <div className="notice notice--good" role="status">
      <p className="notice__title">
        {done === "approved" ? "Approved" : done === "escalated" ? "Rejected — sent to the coordinator" : "Rejected"}
      </p>
      <p className="mb0">The athlete has been told by SMS.</p>
    </div>
  ) : null;

  if (!current || !detail) {
    return (
      <div className="page page--wide stack">
        <CoordinatorNav current="/review" lga={lga} />
        <PageHead
          eyebrow="Review"
          title={<>{queue.length ? "Nothing more here" : "All caught up"}</>}
          app
        />
        {banner}
        <EmptyState title={queue.length ? "You have reached the end of the queue" : "No verifications are waiting in this LGA"}>
          {queue.length ? (
            <p className="mt-3"><a href={`/review?lga=${encodeURIComponent(lga)}`} className="btn btn--primary">Back to the first case</a></p>
          ) : null}
        </EmptyState>
      </div>
    );
  }

  const media = (kind: string) =>
    `/review-media/${encodeURIComponent(lga)}/${encodeURIComponent(detail!.request_id)}/${kind}`;
  const next = `/review?${new URLSearchParams({ lga, n: String(index + 1) }).toString()}`;

  return (
    <div className="page page--wide stack">
      <CoordinatorNav current="/review" lga={lga} />
      <PageHead
        eyebrow={<>Review — {queue.length} waiting</>}
        title={<>Case {index + 1} of {queue.length}</>}
        lede={
          <>
            Waiting {waiting(current.submitted_at)}
            {detail.paid_kobo !== null ? ` · paid ${formatNaira(detail.paid_kobo)} on ${stamp(detail.paid_at)}` : ""}
          </>
        }
        actions={<a href={next} className="btn btn--ghost">Skip for now</a>}
        app
      />
      {banner}

      <div className="split">
      <section className="doc" aria-label="Evidence">
        <div className="doc__body grid grid-2">
          <figure className="evidence">
            <figcaption>Submitted photo</figcaption>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={media("photo")} alt="The photograph the athlete submitted" width={320} />
          </figure>
          <figure className="evidence">
            <figcaption>ID document</figcaption>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={media("document")} alt="The identity document the athlete submitted" width={320} />
          </figure>
        </div>
      </section>

      <div className="stack">
      <section className="doc" aria-label="The case">
        <div className="doc__body">
          <p className="eyebrow">Check against the document</p>
          <dl className="facts">
            <div className="fact"><dt>Name</dt><dd>{detail.full_name}</dd></div>
            <div className="fact">
              <dt>Date of birth</dt>
              <dd>{detail.date_of_birth} · age {detail.age}</dd>
            </div>
            <div className="fact"><dt>KAFRIADA ID</dt><dd><span className="kuid">{detail.kuid}</span></dd></div>
            <div className="fact"><dt>Attempt</dt><dd>{detail.attempt} of 3</dd></div>
          </dl>
          <p className="hint mt-4 mb0">Face matches · name matches · 18 or older</p>
        </div>
      </section>

      <form action={decideAction}>
        <input type="hidden" name="lga" value={lga} />
        <input type="hidden" name="id" value={detail.request_id} />
        <button type="submit" name="decision" value="approve" className="btn btn--primary btn--block">
          Approve
        </button>
      </form>

      <form action={decideAction} className="doc">
        <div className="doc__body">
          <input type="hidden" name="lga" value={lga} />
          <input type="hidden" name="id" value={detail.request_id} />
          <div className="field">
            <label htmlFor="reason">Reject with a reason</label>
            <span className="hint">The athlete reads this exactly as you write it.</span>
            <textarea id="reason" name="reason" maxLength={1000} required />
          </div>
          <button type="submit" name="decision" value="reject" className="btn btn--ghost btn--block">
            Reject with reason
          </button>
        </div>
      </form>
      </div>
      </div>
    </div>
  );
}

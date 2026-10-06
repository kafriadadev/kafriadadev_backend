import { SubmitButton } from "@/components/SubmitButton";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import {
  ApiError,
  getMe,
  getVerification,
  type FileStatus,
  type Me,
  type Verification,
} from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";
import { resubmitAction, uploadAction } from "./actions";

export const metadata: Metadata = { title: "Get verified" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

const when = (iso: string | null): string =>
  iso
    ? new Date(iso).toLocaleString("en-GB", {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Africa/Lagos",
      })
    : "";

/**
 * Verification, whichever step the athlete is on (VER-01, 02, 04 and 05).
 *
 * One address that reads the API's own record of where they stand and shows the
 * matching screen. It never decides anything itself: the state is the API's, and it
 * moves only when a payment settles or a reviewer decides. Every action here is a
 * plain form, so it works with JavaScript off.
 */
export default async function VerifyPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let me: Me;
  let v: Verification;
  try {
    [me, v] = await Promise.all([getMe(token), getVerification(token)]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    if (error instanceof ApiError && error.status === 404) {
      return (
        <div>
          <h1>Get verified</h1>
          <div role="status">
            <p>Only athletes can be verified</p>
            <p>This account has no athlete record.</p>
          </div>
        </div>
      );
    }
    throw error;
  }

  const error = one(params.error);
  const saved = one(params.saved);

  return (
    <div>
      <div>
        <a href="/me">My account</a>
        <p>Verification</p>
      </div>

      {error ? (
        <div role="alert" tabIndex={-1}>
          <p>That did not work</p>
          <p>{error}</p>
        </div>
      ) : saved ? (
        <div role="status">
          <p>Received</p>
          <p>Your file is saved. You can add the other one now.</p>
        </div>
      ) : null}

      {v.state === "under_review" ? (
        <UnderReview v={v} me={me} />
      ) : v.state === "approved" ? (
        <Approved me={me} />
      ) : v.state === "escalated" ? (
        <Escalated v={v} />
      ) : v.state === "rejected" ? (
        <Rejected v={v} />
      ) : (
        <Start v={v} withdrawn={v.state === "revoked"} />
      )}

    </div>
  );
}

function fileLabel(status: FileStatus): string {
  switch (status) {
    case "ready": return "Added";
    case "uploaded":
    case "pending": return "Received — getting it ready";
    case "unreadable": return "We could not read that file — please send another";
    default: return "Not added yet";
  }
}

/** The two file boxes. Shared by the first submission and by a resubmission. */
function UploadForm({ v }: { v: Verification }) {
  return (
    <form action={uploadAction} encType="multipart/form-data">
      <div>
        <div>
          <label htmlFor="photo">Your photo</label>
          <span>Face clearly visible, no cap, no sunglasses.</span>
          <input id="photo" name="photo" type="file" accept="image/jpeg,image/png,image/webp" capture="user" />
          <span>{fileLabel(v.photo)}</span>
        </div>

        <div>
          <label htmlFor="document">Your ID document</label>
          <span>NIN slip, voter&rsquo;s card, driver&rsquo;s licence or passport.</span>
          <input id="document" name="document" type="file" accept="image/jpeg,image/png,image/webp" />
          <span>{fileLabel(v.document)}</span>
        </div>

        <SubmitButton pending="Uploading your files…" detail="Please keep this page open. This can take a few seconds.">Save my files</SubmitButton>
        <p>
          Maximum 10MB per image. Your document is used only to check your identity and age, and is
          deleted 30 days after a decision. Your photo stays on your profile.
        </p>
      </div>
    </form>
  );
}

function Start({ v, withdrawn }: { v: Verification; withdrawn: boolean }) {
  const processing = [v.photo, v.document].some((s) => s === "uploaded" || s === "pending");
  return (
    <>
      <h1>Get verified</h1>
      {withdrawn ? (
        <div role="status">
          <p>Your earlier verification was withdrawn</p>
          <p>You can start again below.</p>
        </div>
      ) : null}

      <section aria-label="What you get">
        <div>
          <p>Add your photo and verified badge</p>
          <ul>
            <li>Your photo on your public profile</li>
            <li>A verified badge scouts can trust</li>
            <li>Checked by your LGA coordinator</li>
          </ul>
          <dl>
            <div>
              <dt>One payment. No renewal.</dt>
              <dd><span>{formatNaira(v.price_kobo)}</span></dd>
            </div>
          </dl>
        </div>
      </section>

      <h2>Step 1 of 2 — your photo and document</h2>
      <UploadForm v={v} />

      {processing ? (
        <p>
          We are getting your files ready. <a href="/verify">Check again</a>
        </p>
      ) : null}

      {v.ready_to_pay ? (
        <a href="/pay">Continue to payment</a>
      ) : (
        <p>Add both files to continue to payment.</p>
      )}
    </>
  );
}

function UnderReview({ v, me }: { v: Verification; me: Me }) {
  return (
    <>
      <h1>Under review</h1>
      <div role="status">
        <p>Your LGA coordinator is checking your documents</p>
        <p>Usually decided within 24 hours.</p>
      </div>

      <section aria-label="Progress">
        <div>
          <p>Progress</p>
          <ol>
            <li data-done="true">Documents received</li>
            <li data-done="true">
              {v.paid_amount_kobo !== null ? `${formatNaira(v.paid_amount_kobo)} paid` : "Paid"}
              {v.paid_at ? ` — ${when(v.paid_at)}` : ""}
            </li>
            <li data-now="true">Being checked{v.attempt > 1 ? ` (attempt ${v.attempt} of 3)` : ""}</li>
            <li data-todo="true">Photo goes live</li>
          </ol>
          <p>
            We will send an SMS to {me.phone} when a decision is made. You do not need to keep
            this page open.
          </p>
        </div>
      </section>
    </>
  );
}

function Approved({ me }: { me: Me }) {
  return (
    <>
      <h1>You are verified</h1>
      <div role="status">
        <p>Your photo and badge are live</p>
        <p>Anyone who scans your card now sees your photograph.</p>
        {me.kuid ? (
          <a href={`/a/${encodeURIComponent(me.kuid)}`}>
            See my public profile
          </a>
        ) : null}
      </div>
    </>
  );
}

function Escalated({ v }: { v: Verification }) {
  return (
    <>
      <h1>Please see your coordinator</h1>
      <div role="status">
        <p>We could not approve this after three tries</p>
        <p>
          Your LGA coordinator will help you in person. You do not need to pay again.
        </p>
        {v.reason ? (
          <>
            <p>The reviewer wrote:</p>
            <blockquote>{v.reason}</blockquote>
          </>
        ) : null}
      </div>
    </>
  );
}

function Rejected({ v }: { v: Verification }) {
  const ready = v.photo === "ready" && v.document === "ready";
  return (
    <>
      <h1>Not approved</h1>
      <div role="status">
        <p>Reason from the reviewer</p>
        <blockquote>{v.reason}</blockquote>
        <p>
          <strong>You do not pay again.</strong> Your {formatNaira(v.paid_amount_kobo ?? v.price_kobo)}{" "}
          still covers this. You have {v.attempts_left} more attempt{v.attempts_left === 1 ? "" : "s"}.
        </p>
      </div>

      <h2>Replace your files</h2>
      <UploadForm v={v} />

      <form action={resubmitAction}>
        <SubmitButton disabled={!ready} pending="Sending for review…">
          Resubmit for review
        </SubmitButton>
        {!ready ? (
          <p>Both files must be added and ready before you can send it again.</p>
        ) : null}
      </form>
    </>
  );
}

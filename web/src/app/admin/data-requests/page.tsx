import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AdminShell } from "@/components/AdminNav";
import { Flash } from "@/components/Flash";
import { NoAccess } from "@/components/NoAccess";
import { PageHead } from "@/components/PageHead";
import { buttonClass } from "@/components/ui/Button";
import { ApiError, type DataRequestPerson, findDataRequestPerson, getMe } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { eraseAction } from "./actions";

export const metadata: Metadata = { title: "Data requests" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

const CHANNELS = [
  ["in_person", "In person"],
  ["phone", "By phone"],
  ["email", "By email"],
  ["letter", "By letter"],
] as const;
const channel = (code: string): string => CHANNELS.find(([c]) => c === code)?.[1] ?? code;

const at = (iso: string): string =>
  new Date(iso).toLocaleString("en-GB", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lagos",
  });

function ChannelField({ id }: { id: string }) {
  return (
    <div>
      <label htmlFor={id}>How the request arrived</label>
      <select id={id} name="received_via" defaultValue="in_person" required>
        {CHANNELS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </div>
  );
}

/**
 * Data requests (ADM-07). Find the person, then either hand them a copy of
 * everything held about them, or erase them. Erasure is anonymisation, and the
 * screen says exactly what it removes and what it keeps before it is done.
 */
export default async function DataRequestsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let isAdmin = false;
  try {
    isAdmin = (await getMe(token)).roles.some((r) => r.role === "super_admin");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }
  if (!isAdmin) return <NoAccess title="Data requests" message="Only a super administrator can handle a data request." />;

  const q = one(params.q).trim();
  const error = one(params.error);
  let person: DataRequestPerson | null = null;
  let notFound = false;
  if (q) {
    try {
      person = await findDataRequestPerson(token, q);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) notFound = true;
      else throw caught;
    }
  }

  return (
    <AdminShell current="/admin/data-requests">
      <PageHead
        eyebrow="Administrator"
        title="Data requests"
        lede="A person may ask for a copy of what KAFRIADA NET holds about them, or for it to be erased. Check who they are before you act on either."
        app
      />

      {one(params.erased) ? (
        <Flash variant="good" title="Erased">
          <p>The person&rsquo;s details have been removed. The ID, payments and audit trail are kept.</p>
        </Flash>
      ) : null}
      {error ? (
        <Flash variant="bad" title="That did not work">
          <p>{error}</p>
        </Flash>
      ) : null}

      <form method="get" role="search">
        <div>
          <label htmlFor="q">KAFRIADA NET ID, phone number or email address</label>
          <input id="q" name="q" defaultValue={q} required />
        </div>
        <button type="submit">Find</button>
      </form>

      {notFound ? (
        <Flash variant="warn" title="Not found">
          <p>Nobody matches. An erased person can only be found by their ID.</p>
        </Flash>
      ) : null}

      {person ? (
        <>
          <section aria-labelledby="person">
            <h2 id="person">{person.full_name}</h2>
            <dl>
              <div><dt>KAFRIADA NET ID</dt><dd>{person.kuid ? <span className="whitespace-nowrap font-mono">{person.kuid}</span> : "None"}</dd></div>
              <div><dt>Roles</dt><dd>{person.roles.length ? person.roles.join(", ") : "None"}</dd></div>
              <div><dt>Registered</dt><dd>{new Date(person.registered_on).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "Africa/Lagos" })}</dd></div>
              <div><dt>Status</dt><dd>{person.anonymised ? "Erased" : "Active"}</dd></div>
            </dl>
          </section>

          {person.requests.length ? (
            <section aria-labelledby="history">
              <h2 id="history">Requests already handled</h2>
              <table>
                <caption className="sr-only">Requests already handled for this person</caption>
                <thead><tr><th>When</th><th>Request</th><th>Arrived</th><th>Handled by</th><th>Note</th></tr></thead>
                <tbody>
                  {person.requests.map((r) => (
                    <tr key={`${r.handled_at}-${r.kind}`}>
                      <td data-label="When"><span>{at(r.handled_at)}</span></td>
                      <td data-label="Request"><span>{r.kind === "export" ? "Copy handed over" : "Erased"}</span></td>
                      <td data-label="Arrived"><span>{channel(r.received_via)}</span></td>
                      <td data-label="Handled by"><span>{r.handled_by}</span></td>
                      <td data-label="Note"><span>{r.note ?? ""}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ) : null}

          <section aria-labelledby="export">
            <h2 id="export">Give them a copy</h2>
            <p>Downloads everything held about this person as a JSON file. The hand-over is recorded.</p>
            <form method="post" action="/admin/data-requests/export">
              <input type="hidden" name="user_id" value={person.user_id} />
              <input type="hidden" name="q" value={q} />
              <ChannelField id="export_via" />
              <div>
                <label htmlFor="export_note">Note (optional)</label>
                <textarea id="export_note" name="note" maxLength={1000} />
              </div>
              <button type="submit">Download a copy</button>
            </form>
          </section>

          {person.anonymised ? null : (
            <section aria-labelledby="erase">
              <h2 id="erase">Erase this person</h2>
              <div className="my-4 rounded-card border-2 border-l-[6px] border-danger bg-danger-bg p-4">
                <p className="font-bold">This will</p>
                <ul className="mt-2 list-disc space-y-1 pl-6">
                  <li>Remove their name, phone number, email, password, date of birth, address and emergency contact</li>
                  <li>Delete their photo and identity document, and any message waiting to be sent to them</li>
                  <li>Sign them out everywhere, revoke their roles and release them from their club</li>
                  <li>Withdraw their verification and take down their public profile and card</li>
                  <li><strong>Keep</strong> the ID itself, their payments and the audit trail, as the privacy notice states</li>
                  <li><strong>Not</strong> be reversible</li>
                </ul>
              </div>
              <form action={eraseAction}>
                <input type="hidden" name="user_id" value={person.user_id} />
                <input type="hidden" name="q" value={q} />
                <ChannelField id="erase_via" />
                <div>
                  <label htmlFor="erase_note">Who asked, and how you checked it was them</label>
                  <span>Kept permanently.</span>
                  <textarea id="erase_note" name="note" maxLength={1000} required />
                </div>
                <div>
                  <label htmlFor="current_password">Your password</label>
                  <input id="current_password" name="current_password" type="password" autoComplete="current-password" required />
                </div>
                <button type="submit" className={buttonClass({ variant: "danger" })}>Erase this person</button>
              </form>
            </section>
          )}
        </>
      ) : null}
    </AdminShell>
  );
}

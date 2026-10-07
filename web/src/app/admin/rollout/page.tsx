import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AdminShell } from "@/components/AdminNav";
import { Flash } from "@/components/Flash";
import { NoAccess } from "@/components/NoAccess";
import { PageHead } from "@/components/PageHead";
import { Iso } from "@/components/iso/Iso";
import { rollout } from "@/components/iso/scenes";
import { buttonClass } from "@/components/ui/Button";
import { ApiError, getRollout, type RolloutLga } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { rolloutAction } from "./actions";

export const metadata: Metadata = { title: "LGA rollout" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

const onDate = (iso: string): string =>
  new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "Africa/Lagos" });

/**
 * LGA rollout (ADM-05). Which LGAs accept registrations, wave by wave. Choosing
 * one opens a confirmation below the table that says what the change does, then
 * asks for a reason and the administrator's password.
 */
export default async function RolloutPage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let lgas: RolloutLga[];
  try {
    lgas = await getRollout(token);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403) return <NoAccess title="LGA rollout" message="Only a super administrator can open or close an LGA." />;
    }
    throw error;
  }

  const chosen = lgas.find((l) => l.id === one(params.lga)) ?? null;
  const error = one(params.error);
  const done = one(params.done);
  const open = lgas.filter((l) => l.is_open);

  return (
    <AdminShell current="/admin/rollout">
      <PageHead
        eyebrow="Administrator"
        title="LGA rollout"
        lede={<>{open.length} of {lgas.length} LGAs accept registrations. Opening or closing one takes effect immediately.</>}
        app
      />

      {done ? (
        <Flash variant="good" title={one(params.opened) === "true" ? "Opened" : "Closed"}>
          <p>{one(params.opened) === "true" ? `${done} now accepts registrations.` : `${done} no longer accepts registrations.`}</p>
        </Flash>
      ) : null}
      {error ? (
        <Flash variant="bad" title="That did not work">
          <p>{error}</p>
        </Flash>
      ) : null}

      {chosen ? (
        <section aria-labelledby="confirm" className="mb-8">
          <h2 id="confirm">{chosen.is_open ? `Close ${chosen.name}` : `Open ${chosen.name}`}</h2>
          <div className="my-4 rounded-card border-2 border-l-[6px] border-[var(--boot)] bg-warn-bg p-4 text-on-warn">
            <p className="font-bold">This will</p>
            {chosen.is_open ? (
              <ul className="mt-2 list-disc space-y-1 pl-6">
                <li>Stop new registrations in {chosen.name} at once</li>
                <li><strong>Not</strong> affect the {chosen.registered.toLocaleString("en-GB")} athletes already registered there: their IDs, cards and profiles stay valid</li>
              </ul>
            ) : (
              <ul className="mt-2 list-disc space-y-1 pl-6">
                <li>Let anyone register in {chosen.name} from now on</li>
                <li>Print the code <strong className="font-mono">{chosen.code}</strong> into every ID issued there. It can never change afterwards</li>
              </ul>
            )}
          </div>
          <form action={rolloutAction}>
            <input type="hidden" name="lga" value={chosen.id} />
            <input type="hidden" name="open" value={String(!chosen.is_open)} />
            <div>
              <label htmlFor="reason">Reason</label>
              <span>Kept permanently in the audit log.</span>
              <textarea id="reason" name="reason" maxLength={1000} required />
            </div>
            <div>
              <label htmlFor="current_password">Your password</label>
              <input id="current_password" name="current_password" type="password" autoComplete="current-password" required />
            </div>
            <button type="submit" className={buttonClass({ variant: chosen.is_open ? "danger" : "primary" })}>
              {chosen.is_open ? `Close ${chosen.name}` : `Open ${chosen.name}`}
            </button>{" "}
            <a href="/admin/rollout">Cancel</a>
          </form>
        </section>
      ) : null}

      <div data-iso-scope="">
        {/* One plot per LGA, in the table's order; a lit floodlight is an open LGA. Hover a row to find its plot. */}
        <Iso fig={rollout(lgas.map((l) => ({ key: l.id, live: l.is_open })))} name="rollout" className="mx-auto mb-6 max-w-md" />
        <table>
          <caption className="sr-only">Every LGA, by rollout wave</caption>
          <thead>
            <tr><th>Wave</th><th>LGA</th><th>Code</th><th>Registered</th><th>Status</th><th><span className="sr-only">Change</span></th></tr>
          </thead>
          <tbody>
            {lgas.map((l) => (
              <tr key={l.id} data-iso-key={l.id}>
                <td data-label="Wave"><span>{l.wave ?? "None"}</span></td>
                <td data-label=""><strong>{l.name}</strong></td>
                <td data-label="Code"><span className="font-mono">{l.code}</span></td>
                <td data-label="Registered"><span>{l.registered.toLocaleString("en-GB")}</span></td>
                <td data-label="Status">
                  <span>{l.is_open ? `Open${l.went_live_at ? ` since ${onDate(l.went_live_at)}` : ""}` : "Closed"}</span>
                </td>
                <td data-label="">
                  <a href={`/admin/rollout?${new URLSearchParams({ lga: l.id })}#confirm`}>
                    {l.is_open ? "Close" : "Open"}<span className="sr-only"> {l.name}</span>
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AdminShell>
  );
}

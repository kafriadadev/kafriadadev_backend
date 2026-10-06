import { VerificationBadge } from "@/components/VerificationBadge";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { CoordinatorNav } from "@/components/CoordinatorNav";
import { EmptyState } from "@/components/EmptyState";
import { PageHead } from "@/components/PageHead";
import { Pager } from "@/components/Pager";
import { Flash } from "@/components/Flash";
import { ApiError, type AthleteSearch, getMe, searchAthletes } from "@/lib/api";
import { sessionToken } from "@/lib/session";

export const metadata: Metadata = { title: "Find an athlete" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/**
 * Find an athlete (CRD-03): a plain GET form and server-rendered results.
 *
 * Name (partial), KAFRIADA NET ID (partial) or a whole phone number, inside one LGA. An
 * athlete anywhere else comes back as no result at all — never "not permitted" — so
 * this cannot be used to learn who exists elsewhere.
 */
export default async function FindAthletePage({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let own = "";
  try {
    const me = await getMe(token);
    own = me.roles.find((r) => r.scope_kind === "lga")?.scope_id ?? "";
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }

  const lga = one(params.lga) || own;
  const q = one(params.q).trim();
  const page = Math.max(Number.parseInt(one(params.page) || "1", 10) || 1, 1);

  if (!lga) {
    return (
      <div>
        <h1>Find an athlete</h1>
        <Flash variant="warn" title="No LGA to search">
          <p>
            Choose a local government area on <a href="/coordinator">your dashboard</a> first.
          </p>
        </Flash>
      </div>
    );
  }

  let results: AthleteSearch | null = null;
  let denied = false;
  if (q) {
    try {
      results = await searchAthletes(token, lga, q, page);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 401) redirect("/sign-in?ended=1");
        if (error.status === 403 || error.status === 404) denied = true;
        else throw error;
      } else throw error;
    }
  }

  const link = (p: number) =>
    `/coordinator/find?${new URLSearchParams({ lga, q, page: String(p) })}`;

  return (
    <div>
      <CoordinatorNav current="/coordinator/find" lga={lga} />
      <PageHead
        eyebrow="Coordinator"
        title="Find an athlete"
        lede="Searches this local government area only."
        app
      />

      <form method="get" role="search">
        <input type="hidden" name="lga" value={lga} />
        <div>
          <label htmlFor="q">KAFRIADA NET ID, phone or name</label>
          <input id="q" name="q" required minLength={2} defaultValue={q} placeholder="Musa Ibrahim" />
        </div>
        <button type="submit">Search</button>
      </form>

      {denied ? (
        <Flash variant="bad" title="You do not have access to this">
          <p>You can only search your own local government area.</p>
        </Flash>
      ) : null}

      {results && !results.people.length ? <EmptyState title="No results" /> : null}

      {results && results.people.length ? (
        <div>
          <table>
            <thead>
              <tr><th>Name</th><th>KAFRIADA NET ID</th><th>Status</th><th><span>Actions</span></th></tr>
            </thead>
            <tbody>
              {results.people.map((p) => (
                <tr key={p.kuid}>
                  <td data-label="">
                    <span>
                      <strong>{p.full_name}</strong>
                      {p.playing_position ? <><br /><span>{p.playing_position}</span></> : null}
                    </span>
                  </td>
                  <td data-label="ID"><span>{p.kuid}</span></td>
                  <td data-label="Status">
                    <VerificationBadge verified={p.verified} />
                  </td>
                  <td data-label="">
                    <span>
                      <a href={`/a/${encodeURIComponent(p.kuid)}`}>Profile</a>
                      {p.verified ? null : (
                        <a
                          href={`/assist-pay?${new URLSearchParams({ lga, kuid: p.kuid })}`}
                        >
                          Pay for this athlete
                        </a>
                      )}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {results ? (
        <Pager page={page} prev={page > 1 ? link(page - 1) : null} next={results.has_more ? link(page + 1) : null} />
      ) : null}
    </div>
  );
}

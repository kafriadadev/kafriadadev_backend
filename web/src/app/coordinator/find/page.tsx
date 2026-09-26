import type { Metadata } from "next";
import { redirect } from "next/navigation";

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
 * Name (partial), KAFRIADA ID (partial) or a whole phone number, inside one LGA. An
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
      <div className="stack">
        <h1>Find an athlete</h1>
        <Flash variant="warn" title="No LGA to search">
          <p style={{ marginBottom: 0 }}>
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
    <div className="stack">
      <p className="eyebrow">Coordinator</p>
      <h1>Find an athlete</h1>

      <form method="get" className="doc">
        <div className="doc__body">
          <input type="hidden" name="lga" value={lga} />
          <div className="field">
            <label htmlFor="q">KAFRIADA ID, phone or name</label>
            <span className="hint">Searches this local government area only.</span>
            <input id="q" name="q" required minLength={2} defaultValue={q} placeholder="Musa Ibrahim" />
          </div>
          <button type="submit" className="btn btn--primary btn--block">Search</button>
        </div>
      </form>

      {denied ? (
        <Flash variant="bad" title="You do not have access to this">
          <p style={{ marginBottom: 0 }}>You can only search your own local government area.</p>
        </Flash>
      ) : null}

      {results && !results.people.length ? (
        <p className="hint">No results.</p>
      ) : null}

      {results?.people.map((p) => (
        <section className="doc" key={p.kuid} aria-label={p.full_name}>
          <div className="doc__body">
            <p style={{ fontWeight: 700, marginBottom: "var(--s2)" }}>{p.full_name}</p>
            <p style={{ marginBottom: "var(--s2)" }}><span className="kuid">{p.kuid}</span></p>
            <p style={{ marginBottom: "var(--s3)" }}>
              <span className={p.verified ? "pill pill--issued" : "pill pill--pending"}>
                {p.verified ? "Verified" : "Not verified"}
              </span>
              {p.playing_position ? ` ${p.playing_position}` : ""}
            </p>
            <div style={{ display: "flex", gap: "var(--s3)", flexWrap: "wrap" }}>
              <a href={`/a/${encodeURIComponent(p.kuid)}`} className="btn btn--ghost">Open profile</a>
              {p.verified ? null : (
                <a
                  href={`/assist-pay?${new URLSearchParams({ lga, kuid: p.kuid })}`}
                  className="btn btn--ghost"
                >
                  Pay for this athlete
                </a>
              )}
            </div>
          </div>
        </section>
      ))}

      {results && (page > 1 || results.has_more) ? (
        <nav aria-label="Pages" style={{ display: "flex", gap: "var(--s4)" }}>
          {page > 1 ? <a href={link(page - 1)}>Previous</a> : null}
          {results.has_more ? <a href={link(page + 1)}>Next</a> : null}
        </nav>
      ) : null}

      <p><a href={`/coordinator?lga=${encodeURIComponent(lga)}`}>Back to today</a></p>
    </div>
  );
}

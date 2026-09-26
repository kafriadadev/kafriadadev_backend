import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { Flash } from "@/components/Flash";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError, type ClubDashboard, type ClubRosterRow, getClub } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { removeAction } from "./actions";

export const metadata: Metadata = { title: "Club" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

const TABS = [
  { key: "roster", label: "Roster" },
  { key: "invitations", label: "Invitations" },
  { key: "details", label: "Club details" },
] as const;

const STATE_LABEL: Record<ClubRosterRow["state"], string> = {
  verified: "Verified",
  unverified: "Not verified",
  invited: "Invited",
};
const STATE_PILL: Record<ClubRosterRow["state"], string> = {
  verified: "pill pill--issued",
  unverified: "pill pill--pending",
  invited: "pill pill--pending",
};

/**
 * A club's dashboard (CLB-02): numbers, roster, invitations, details.
 *
 * Which club a person may open is the API's decision, made from their own grants; this
 * screen shows whatever the API returns for the id in the address and nothing else.
 */
export default async function ClubPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Search>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let club: ClubDashboard;
  try {
    club = await getClub(token, id);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403 || error.status === 404) {
        return (
          <div className="stack">
            <h1>Club</h1>
            <Flash variant="bad" title="You do not have access to this">
              <p style={{ marginBottom: 0 }}>
                You can only open a club you administer. <a href="/me">Back to your account</a>
              </p>
            </Flash>
          </div>
        );
      }
    }
    throw error;
  }

  const tab = TABS.find((t) => t.key === one(query.tab))?.key ?? "roster";
  const base = `/clubs/${encodeURIComponent(club.club_id)}`;
  const players = club.roster.filter((r) => r.state !== "invited");
  const invited = club.roster.filter((r) => r.state === "invited");

  return (
    <div className="stack">
      <p className="eyebrow">Club &middot; {club.sport} &middot; {club.lga_name}</p>
      <h1>{club.name}</h1>

      {one(query.registered) ? (
        <Flash variant="good" title="Club registered">
          <p style={{ marginBottom: 0 }}>You are now this club&rsquo;s administrator.</p>
        </Flash>
      ) : null}

      {one(query.invited) ? (
        <Flash variant="good" title="Invitation sent">
          <p style={{ marginBottom: 0 }}>The player appears on your roster once they accept.</p>
        </Flash>
      ) : null}
      {one(query.saved) ? (
        <Flash variant="good" title="Details saved">
          <p style={{ marginBottom: 0 }}>The club&rsquo;s details are updated.</p>
        </Flash>
      ) : null}
      {one(query.removed) ? (
        <Flash variant="good" title="Done">
          <p style={{ marginBottom: 0 }}>The roster has been updated.</p>
        </Flash>
      ) : null}
      {one(query.error) ? (
        <Flash variant="bad" title="That did not work">
          <p style={{ marginBottom: 0 }}>{one(query.error)}</p>
        </Flash>
      ) : null}

      {club.status === "pending_review" ? (
        <Flash variant="warn" title="Waiting for approval">
          <p style={{ marginBottom: 0 }}>
            An administrator reviews every new club. Once it is approved you can build a roster.
          </p>
        </Flash>
      ) : club.status === "suspended" ? (
        <Flash variant="bad" title="This club is suspended">
          <p style={{ marginBottom: 0 }}>Contact your local government area coordinator.</p>
        </Flash>
      ) : null}

      <section className="doc" aria-label="Club summary">
        <div className="doc__body">
          <p className="eyebrow">{club.verified ? "Verified club" : "Not a verified club"}</p>
          <dl className="facts">
            <div className="fact"><dt>Players</dt><dd>{club.players}</dd></div>
            <div className="fact"><dt>Verified players</dt><dd>{club.verified_players}</dd></div>
            <div className="fact"><dt>Invitations out</dt><dd>{club.invites_out}</dd></div>
          </dl>
        </div>
      </section>

      {club.status === "approved" ? (
        <p style={{ display: "flex", gap: "var(--s3)", flexWrap: "wrap" }}>
          <a href={`${base}/invite`} className="btn btn--primary">Add a player</a>
          {club.verified ? null : (
            <a href={`${base}/verify`} className="btn btn--ghost">Verify club</a>
          )}
        </p>
      ) : null}

      <nav aria-label="Club sections" style={{ display: "flex", gap: "var(--s4)", flexWrap: "wrap" }}>
        {TABS.map((t) =>
          t.key === tab ? (
            <strong key={t.key} aria-current="page">{t.label}</strong>
          ) : (
            <a key={t.key} href={`${base}?tab=${t.key}`}>{t.label}</a>
          ),
        )}
      </nav>

      {tab === "roster" ? (
        players.length ? (
          <RosterList rows={players} clubId={club.club_id} tab="roster" action="Remove" />
        ) : (
          <p className="hint">
            No players yet. A player joins by accepting an invitation from this club.
          </p>
        )
      ) : null}

      {tab === "invitations" ? (
        invited.length ? (
          <RosterList rows={invited} clubId={club.club_id} tab="invitations" action="Withdraw" />
        ) : (
          <p className="hint">No invitations are waiting for an answer.</p>
        )
      ) : null}

      {tab === "details" ? (
        <section className="doc" aria-label="Club details">
          <div className="doc__body">
            <dl className="facts">
              <div className="fact"><dt>Name</dt><dd>{club.name}</dd></div>
              <div className="fact"><dt>Sport</dt><dd>{club.sport}</dd></div>
              <div className="fact"><dt>Area</dt><dd>{club.lga_name}</dd></div>
              {club.year_founded ? (
                <div className="fact"><dt>Founded</dt><dd>{club.year_founded}</dd></div>
              ) : null}
              <div className="fact"><dt>Contact</dt><dd>{club.contact_phone}</dd></div>
            </dl>
            <p style={{ marginTop: "var(--s4)", marginBottom: 0 }}>
              <a href={`${base}/edit`} className="btn btn--ghost">Edit details</a>
            </p>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function RosterList({
  rows,
  clubId,
  tab,
  action,
}: {
  rows: ClubRosterRow[];
  clubId: string;
  tab: string;
  action: string;
}) {
  return (
    <div className="stack">
      {rows.map((r) => (
        <section className="doc" key={r.kuid} aria-label={r.full_name}>
          <div className="doc__body">
            <p style={{ fontWeight: 700, marginBottom: "var(--s2)" }}>{r.full_name}</p>
            <p style={{ marginBottom: "var(--s2)" }}><span className="kuid">{r.kuid}</span></p>
            <p style={{ marginBottom: 0 }}>
              <span className={STATE_PILL[r.state]}>{STATE_LABEL[r.state]}</span>
              {r.position ? ` ${r.position}` : ""}
            </p>
            <form action={removeAction} style={{ marginTop: "var(--s3)" }}>
              <input type="hidden" name="club" value={clubId} />
              <input type="hidden" name="roster" value={r.roster_id} />
              <input type="hidden" name="tab" value={tab} />
              <SubmitButton className="btn btn--ghost" pending="Updating the roster…">
                {action}
              </SubmitButton>
            </form>
          </div>
        </section>
      ))}
    </div>
  );
}

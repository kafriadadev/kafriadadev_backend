import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { EmptyState } from "@/components/EmptyState";
import { PageHead } from "@/components/PageHead";
import { Stat } from "@/components/Stat";
import { SubNav } from "@/components/SubNav";
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
  unverified: "Unverified",
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
          <div className="page stack">
            <h1>Club</h1>
            <Flash variant="bad" title="You do not have access to this">
              <p className="mb0">
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
    <div className="page page--wide stack">
      <PageHead
        back={{ href: "/clubs", label: "My clubs" }}
        eyebrow={<>Club &middot; {club.sport} &middot; {club.lga_name}</>}
        title={club.name}
        app
        actions={
          club.status === "approved" ? (
            <>
              <a href={`${base}/invite`} className="btn btn--primary">Add a player</a>
              {club.verified ? null : (
                <a href={`${base}/verify`} className="btn btn--ghost">Verify club</a>
              )}
            </>
          ) : undefined
        }
      />

      {one(query.registered) ? (
        <Flash variant="good" title="Club registered">
          <p className="mb0">You are now this club&rsquo;s administrator.</p>
        </Flash>
      ) : null}

      {one(query.invited) ? (
        <Flash variant="good" title="Invitation sent">
          <p className="mb0">The player appears on your roster once they accept.</p>
        </Flash>
      ) : null}
      {one(query.saved) ? (
        <Flash variant="good" title="Details saved">
          <p className="mb0">The club&rsquo;s details are updated.</p>
        </Flash>
      ) : null}
      {one(query.removed) ? (
        <Flash variant="good" title="Done">
          <p className="mb0">The roster has been updated.</p>
        </Flash>
      ) : null}
      {one(query.error) ? (
        <Flash variant="bad" title="That did not work">
          <p className="mb0">{one(query.error)}</p>
        </Flash>
      ) : null}

      {club.status === "pending_review" ? (
        <Flash variant="warn" title="Waiting for approval">
          <p className="mb0">
            An administrator reviews every new club. Once it is approved you can build a roster.
          </p>
        </Flash>
      ) : club.status === "suspended" ? (
        <Flash variant="bad" title="This club is suspended">
          <p className="mb0">Contact your local government area coordinator.</p>
        </Flash>
      ) : null}

      <div className="stats">
        <Stat
          label="Club status"
          value={club.verified ? "Verified" : "Not verified"}
          tone={club.verified ? "good" : undefined}
        />
        <Stat label="Players" value={club.players} />
        <Stat label="Verified players" value={club.verified_players} />
        <Stat label="Invitations out" value={club.invites_out} />
      </div>

      <SubNav
        links={TABS.map((t) => ({ href: `${base}?tab=${t.key}`, label: t.label }))}
        current={`${base}?tab=${tab}`}
        label="Club sections"
      />

      {tab === "roster" ? (
        players.length ? (
          <RosterList rows={players} clubId={club.club_id} tab="roster" action="Remove" />
        ) : (
          <EmptyState title="No players yet">
            <p className="small">A player joins by accepting an invitation from this club.</p>
          </EmptyState>
        )
      ) : null}

      {tab === "invitations" ? (
        invited.length ? (
          <RosterList rows={invited} clubId={club.club_id} tab="invitations" action="Withdraw" />
        ) : (
          <EmptyState title="No invitations are waiting for an answer" />
        )
      ) : null}

      {tab === "details" ? (
        <section className="doc narrow" aria-label="Club details">
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
            <p className="mt-4 mb0">
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
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr><th>Player</th><th>KAFRIADA ID</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.kuid}>
              <td data-label="">
                <span>
                  <strong>{r.full_name}</strong>
                  {r.position ? <><br /><span className="hint">{r.position}</span></> : null}
                </span>
              </td>
              <td data-label="ID"><span className="kuid">{r.kuid}</span></td>
              <td data-label="Status"><span className={STATE_PILL[r.state]}>{STATE_LABEL[r.state]}</span></td>
              <td data-label="">
                <form action={removeAction}>
                  <input type="hidden" name="club" value={clubId} />
                  <input type="hidden" name="roster" value={r.roster_id} />
                  <input type="hidden" name="tab" value={tab} />
                  <SubmitButton className="btn btn--ghost btn--sm" pending="Updating the roster…">
                    {action}
                  </SubmitButton>
                </form>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

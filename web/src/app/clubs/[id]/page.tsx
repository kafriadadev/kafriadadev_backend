import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { EmptyState } from "@/components/EmptyState";
import { AGE_GROUPS, CATEGORIES, CLUB_LEVELS, CLUB_TYPES } from "@/lib/clubProfile";
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
          <div>
            <h1>Club</h1>
            <Flash variant="bad" title="You do not have access to this">
              <p>
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
    <div>
      <PageHead
        back={{ href: "/clubs", label: "My clubs" }}
        eyebrow={<>Club &middot; {club.sport} &middot; {club.lga_name}</>}
        title={club.name}
        app
        actions={
          club.status === "approved" ? (
            <>
              <a href={`${base}/invite`}>Add a player</a>
              {club.verified ? null : (
                <a href={`${base}/verify`}>Verify club</a>
              )}
            </>
          ) : undefined
        }
      />

      {one(query.registered) ? (
        <Flash variant="good" title="Club registered">
          <p>You are now this club&rsquo;s administrator.</p>
        </Flash>
      ) : null}

      {one(query.invited) ? (
        <Flash variant="good" title="Invitation sent">
          <p>The player appears on your roster once they accept.</p>
        </Flash>
      ) : null}
      {one(query.saved) ? (
        <Flash variant="good" title="Details saved">
          <p>The club&rsquo;s details are updated.</p>
        </Flash>
      ) : null}
      {one(query.removed) ? (
        <Flash variant="good" title="Done">
          <p>The roster has been updated.</p>
        </Flash>
      ) : null}
      {one(query.error) ? (
        <Flash variant="bad" title="That did not work">
          <p>{one(query.error)}</p>
        </Flash>
      ) : null}

      {club.status === "pending_review" ? (
        <Flash variant="warn" title="Waiting for approval">
          <p>
            An administrator reviews every new club. Once it is approved you can build a roster.
          </p>
        </Flash>
      ) : club.status === "suspended" ? (
        <Flash variant="bad" title="This club is suspended">
          <p>Contact your local government area coordinator.</p>
        </Flash>
      ) : null}

      <div>
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
            <p>A player joins by accepting an invitation from this club.</p>
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
        <section aria-label="Club details">
          <div>
            {(() => {
              const p = (club.profile ?? {}) as Record<string, unknown>;
              const t = (v: unknown): string | null =>
                v === null || v === undefined || v === "" ? null : String(v);
              const label = (map: Record<string, string>, v: unknown) =>
                t(v) ? (map[String(v)] ?? String(v)) : null;
              const groups = Array.isArray(p.age_groups)
                ? (p.age_groups as string[]).map((g) => AGE_GROUPS[g] ?? g).join(", ")
                : null;
              const rows: [string, string | null][] = [
                ["Registered name", club.name],
                ["Short name", t(p.short_name)],
                ["Kind", label(CLUB_TYPES, p.type)],
                ["Sport", club.sport],
                ["Category", label(CATEGORIES, p.category)],
                ["Age groups", groups],
                ["Level", label(CLUB_LEVELS, p.level)],
                ["Founded", club.year_founded ? String(club.year_founded) : null],
                ["Home ground", [t(p.ground_name), t(p.ground_address), t(p.town)].filter(Boolean).join(", ") || null],
                ["Area", club.lga_name],
                ["Club phone", club.contact_phone],
                ["Club email", t(p.club_email)],
                ["Registration number", t(p.cac_number)],
                ["Affiliation", t(p.affiliation)],
                ["Colours", t(p.colours)],
                ["Website", t(p.website)],
                ["Representative's role", t(p.rep_role)],
                ["Second official", t(p.official2_name)
                  ? `${t(p.official2_name)} (${t(p.official2_role) ?? ""}), ${t(p.official2_phone) ?? ""}`
                  : null],
              ];
              const missing = rows.filter(([, v]) => v === null).length;
              return (
                <>
                  {missing ? (
                    <div>
                      <p>The club&rsquo;s record is incomplete</p>
                      <p>Fill in the missing details so reviewers have the full picture.</p>
                    </div>
                  ) : null}
                  <div>
                    {[rows.slice(0, 9), rows.slice(9)].map((half, i) => (
                      <dl key={i}>
                        {half.map(([k, v]) => (
                          <div key={k}>
                            <dt>{k}</dt>
                            <dd>{v ?? <span>Not given</span>}</dd>
                          </div>
                        ))}
                      </dl>
                    ))}
                  </div>
                </>
              );
            })()}
            <p>
              <a href={`${base}/edit`}>Edit details</a>
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
    <div>
      <table>
        <thead>
          <tr><th>Player</th><th>KAFRIADA NET ID</th><th>Status</th><th><span>Actions</span></th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.kuid}>
              <td data-label="">
                <span>
                  <strong>{r.full_name}</strong>
                  {r.position ? <><br /><span>{r.position}</span></> : null}
                </span>
              </td>
              <td data-label="ID"><span>{r.kuid}</span></td>
              <td data-label="Status"><span>{STATE_LABEL[r.state]}</span></td>
              <td data-label="">
                <form action={removeAction}>
                  <input type="hidden" name="club" value={clubId} />
                  <input type="hidden" name="roster" value={r.roster_id} />
                  <input type="hidden" name="tab" value={tab} />
                  <SubmitButton pending="Updating the roster…">
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

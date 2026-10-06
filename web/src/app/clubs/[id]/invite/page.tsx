import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PageHead } from "@/components/PageHead";
import { NoAccess } from "@/components/NoAccess";
import { Flash } from "@/components/Flash";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError, type PlayerMatch, findPlayer } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { inviteAction } from "../actions";

export const metadata: Metadata = { title: "Add a player" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/**
 * Invite a player (CLB-03).
 *
 * A search box that only ever returns one exact match: a full KAFRIADA NET ID or a phone
 * number. There is no browsing and no partial search by design — a club administrator
 * who could list players would be reading a directory. The player must accept before
 * they appear on the roster.
 */
export default async function InvitePage({
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

  const q = one(query.q).trim();
  const error = one(query.error);
  let match: PlayerMatch | null = null;
  let notFound = false;
  let denied = false;

  if (q) {
    try {
      match = await findPlayer(token, id, q);
    } catch (caught) {
      if (caught instanceof ApiError) {
        if (caught.status === 401) redirect("/sign-in?ended=1");
        if (caught.status === 404) notFound = true;
        else if (caught.status === 403) denied = true;
        else throw caught;
      } else throw caught;
    }
  }

  const back = `/clubs/${encodeURIComponent(id)}`;

  if (denied) {
    return (
      <NoAccess title="Add a player" message="You can only add players to a club you administer." />
    );
  }

  return (
    <div>
      <PageHead
        back={{ href: back, label: "Club" }}
        eyebrow="Club"
        title="Add a player"
      />

      {error ? (
        <Flash variant="bad" title="That did not work">
          <p>{error}</p>
        </Flash>
      ) : null}

      <form method="get">
        <div>
          <div>
            <label htmlFor="q">KAFRIADA NET ID or phone number</label>
            <span>Enter the full ID or number. You cannot browse players.</span>
            <input
              id="q"
              name="q"
              required
              defaultValue={q}
              placeholder="KA-NG-JG-BKD-2026-000123"
            />
          </div>
          <button type="submit">Search</button>
        </div>
      </form>

      {notFound ? (
        <Flash variant="warn" title="No player found">
          <p>Check the ID or number and try again.</p>
        </Flash>
      ) : null}

      {match ? (
        <section aria-label="Player found">
          <div>
            <p>{match.full_name}</p>
            <p><span>{match.kuid}</span></p>
            <p>
              <span>
                {match.verified ? "Verified" : "Not verified"}
              </span>{" "}
              {[match.position, match.lga_name].filter(Boolean).join(" · ")}
            </p>

            {match.state === "on_roster" ? (
              <p>This player is already on your roster.</p>
            ) : match.state === "invited" ? (
              <p>You have already invited this player.</p>
            ) : (
              <form action={inviteAction}>
                <input type="hidden" name="club" value={id} />
                <input type="hidden" name="kuid" value={match.kuid} />
                {match.current_club ? (
                  <p>
                    This player is currently at {match.current_club}. Accepting your invitation
                    will move them to your club.
                  </p>
                ) : null}
                <SubmitButton pending="Sending invitation…">Send invitation</SubmitButton>
                <p>
                  The player must accept before they appear on your roster.
                </p>
              </form>
            )}
          </div>
        </section>
      ) : null}

    </div>
  );
}

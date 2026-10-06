import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { EmptyState } from "@/components/EmptyState";
import { PageHead } from "@/components/PageHead";
import { Flash } from "@/components/Flash";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError, type Membership, type MyClubs, getMyClubs } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { answerAction } from "./actions";

export const metadata: Metadata = { title: "My clubs" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/** My clubs and invitations (ATH-05). Answering an invitation is a plain form post. */
export default async function MyClubsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const query = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let mine: MyClubs;
  try {
    mine = await getMyClubs(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }

  const error = one(query.error);
  const done = one(query.done);

  return (
    <div>
      <PageHead
        back={{ href: "/me", label: "My account" }}
        eyebrow="Clubs"
        title="My clubs"
      />

      {error ? (
        <Flash variant="bad" title="That did not work">
          <p>{error}</p>
        </Flash>
      ) : null}
      {done === "accept" ? (
        <Flash variant="good" title="You have joined the club">
          <p>Your club now shows on your record.</p>
        </Flash>
      ) : null}
      {done === "decline" ? (
        <Flash variant="good" title="Invitation declined">
          <p>It has been removed from your list.</p>
        </Flash>
      ) : null}

      <h2>Current club</h2>
      {mine.current ? (
        <ClubCard m={mine.current} />
      ) : (
        <EmptyState title="You are not on a club roster" />
      )}

      <h2>Invitations</h2>
      {mine.invitations.length ? (
        mine.invitations.map((m) => (
          <ClubCard key={m.roster_id} m={m}>
            {mine.current ? (
              <p>
                Accepting will move you from {mine.current.club_name} to {m.club_name}.
              </p>
            ) : null}
            <div>
              <form action={answerAction}>
                <input type="hidden" name="roster" value={m.roster_id} />
                <input type="hidden" name="answer" value="accept" />
                <SubmitButton pending="Joining…">Accept</SubmitButton>
              </form>
              <form action={answerAction}>
                <input type="hidden" name="roster" value={m.roster_id} />
                <input type="hidden" name="answer" value="decline" />
                <SubmitButton pending="Declining…">Decline</SubmitButton>
              </form>
            </div>
          </ClubCard>
        ))
      ) : (
        <EmptyState title="You have no invitations" />
      )}

    </div>
  );
}

function ClubCard({ m, children }: { m: Membership; children?: React.ReactNode }) {
  return (
    <section aria-label={m.club_name}>
      <div>
        <h2>{m.club_name}</h2>
        <p>
          <span>
            {m.verified_club ? "Verified club" : "Not a verified club"}
          </span>{" "}
          {m.sport} &middot; {m.lga_name}
        </p>
        {children}
      </div>
    </section>
  );
}

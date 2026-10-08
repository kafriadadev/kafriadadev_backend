import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconMapPin, IconShieldCheck, IconShirtSport } from "@/components/icons";
import { Iso } from "@/components/iso/Iso";
import { noClub, noInvitations } from "@/components/iso/scenes";
import { AthleteShell } from "@/components/ui/AthleteShell";
import { Notice } from "@/components/ui/Notice";
import { PageHead } from "@/components/ui/Page";
import { EmptyState } from "@/components/ui/PageState";
import { Pill } from "@/components/ui/Pill";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ApiError, getMe, getMyClubs, type Me, type Membership, type MyClubs } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { answerAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("clubsMine"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
type T = Awaited<ReturnType<typeof getTranslations<"clubsMine">>>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

/**
 * My clubs and invitations (ATH-05). The athlete controls their own roster
 * membership: a club invites, the athlete answers. One club at a time is the
 * database's rule; this screen only warns before a move.
 */
export default async function MyClubsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("clubsMine");
  const query = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  let me: Me;
  let mine: MyClubs;
  try {
    [me, mine] = await Promise.all([getMe(token), getMyClubs(token)]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }
  const error = one(query.error);
  const done = one(query.done);

  return (
    <AthleteShell current="clubs" kuid={me.kuid}>
      <PageHead eyebrow={t("eyebrow")} title={t("title")} />
      <div className="mb-6 empty:hidden">
        {error ? <Notice signal="red" title={t("error")}><p>{error}</p></Notice> : null}
        {done === "accept" ? <Notice signal="done" title={t("accepted")}><p>{t("acceptedText")}</p></Notice> : null}
        {done === "decline" ? <Notice signal="done" title={t("declined")}><p>{t("declinedText")}</p></Notice> : null}
      </div>

      {mine.invitations.length ? (
        <section aria-labelledby="inv" className="mb-10">
          <h2 id="inv" className="text-lg uppercase">{t("invitations")}</h2>
          <ul className="mt-3 space-y-3">
            {mine.invitations.map((m) => (
              <li key={m.roster_id}>
                <ClubCard t={t} m={m} invite>
                  {mine.current ? <p className="mt-2 font-bold">{t("moving", { from: mine.current.club_name, to: m.club_name })}</p> : null}
                  <div className="mt-4 flex flex-wrap gap-3">
                    <form action={answerAction}>
                      <input type="hidden" name="roster" value={m.roster_id} />
                      <input type="hidden" name="answer" value="accept" />
                      <SubmitButton size="md" block={false} pendingLabel={t("accepting")}>{t("accept")}</SubmitButton>
                    </form>
                    <form action={answerAction}>
                      <input type="hidden" name="roster" value={m.roster_id} />
                      <input type="hidden" name="answer" value="decline" />
                      <SubmitButton size="md" block={false} variant="secondary" pendingLabel={t("declining")}>{t("decline")}</SubmitButton>
                    </form>
                  </div>
                </ClubCard>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section aria-labelledby="cur">
        <h2 id="cur" className="text-lg uppercase">{t("current")}</h2>
        <div className="mt-3">
          {mine.current ? (
            <ClubCard t={t} m={mine.current} />
          ) : (
            <EmptyState wideArt art={<Iso fig={noClub()} name="no-club" />} title={t("noClub")}>{t("noClubText")}</EmptyState>
          )}
        </div>
      </section>

      {!mine.invitations.length ? (
        <section aria-labelledby="none" className="mt-10">
          <h2 id="none" className="text-lg uppercase">{t("invitations")}</h2>
          <div className="mt-3"><EmptyState wideArt art={<Iso fig={noInvitations()} name="no-invitations" />} title={t("noInvitations")}>{t("noInvitationsText")}</EmptyState></div>
        </section>
      ) : null}
    </AthleteShell>
  );
}

function ClubCard({ t, m, invite, children }: { t: T; m: Membership; invite?: boolean; children?: React.ReactNode }) {
  return (
    <article aria-label={m.club_name} className="rounded-card border-2 border-line p-4">
      <div className="flex items-start gap-3">
        <span className="grid size-12 shrink-0 place-items-center rounded-full bg-pitch text-on-pitch" aria-hidden="true"><IconShirtSport /></span>
        <div className="min-w-0 flex-1">
          <h3 className="text-xl uppercase">{m.club_name}</h3>
          {invite ? <p className="text-muted">{t("wants")}</p> : null}
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
            <span className="inline-flex items-center gap-1"><IconMapPin size={16} aria-hidden="true" />{m.lga_name}</span>
            {m.verified_club ? (
              <Pill tone="good" icon={<IconShieldCheck size={16} aria-hidden="true" />}>{t("verifiedClub")}</Pill>
            ) : (
              <Pill>{t("unverifiedClub")}</Pill>
            )}
          </p>
          {children}
        </div>
      </div>
    </article>
  );
}

import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconLock, IconSearch, IconSend } from "@/components/icons";
import { EmptyNet, RaisedFlag } from "@/components/illustrations";
import { AthleteShell } from "@/components/ui/AthleteShell";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { PageHead } from "@/components/ui/Page";
import { EmptyState, PageState } from "@/components/ui/PageState";
import { PlayerCard } from "@/components/ui/PlayerCard";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ApiError, findPlayer, getMe, type PlayerMatch } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { inviteAction } from "../actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("invite"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

/**
 * Invite a player (CLB-03). One exact match only, a full ID or phone number:
 * a club can find a player it already knows, never browse the register. The
 * player must accept before they join the squad.
 */
export default async function InvitePage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Search> }) {
  const t = await getTranslations("invite");
  const tu = await getTranslations("ui");
  const { id } = await params;
  const query = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  const q = one(query.q).trim();
  const error = one(query.error);
  let match: PlayerMatch | null = null;
  let notFound = false;
  let kuid: string | null = null;
  try {
    kuid = (await getMe(token)).kuid;
    if (q) match = await findPlayer(token, id, q);
  } catch (caught) {
    if (!(caught instanceof ApiError)) throw caught;
    if (caught.status === 401) redirect("/sign-in?ended=1");
    if (caught.status === 403) {
      return (
        <PageState art={<RaisedFlag />} title={t("title")} action={<Button href="/me" size="lg" block>{t("back")}</Button>}>
          {t("noAccess")}
        </PageState>
      );
    }
    if (caught.status === 404) notFound = true;
    else throw caught;
  }
  const back = `/clubs/${encodeURIComponent(id)}`;

  return (
    <AthleteShell current="clubs" kuid={kuid}>
      <PageHead back={{ href: back, label: t("back") }} eyebrow={t("eyebrow")} title={t("title")} />
      {error ? <Notice signal="red" title={t("error")} className="mb-6"><p>{error}</p></Notice> : null}

      <form method="get" className="space-y-4">
        <Field name="q" label={t("label")} hint={t("hint")}>
          {(a) => <Input {...a} required defaultValue={q} autoCapitalize="characters" spellCheck={false} placeholder="KA-NG-JG-BKD-2026-000123" className="font-mono" />}
        </Field>
        <Button type="submit" size="lg" block icon={<IconSearch size={20} aria-hidden="true" />}>{t("search")}</Button>
      </form>
      <p className="mt-3 flex items-start gap-2 text-xs text-muted"><IconLock size={16} className="mt-0.5 shrink-0" aria-hidden="true" />{t("privacy")}</p>

      <div className="mt-8">
        {notFound ? (
          <EmptyState art={<EmptyNet />} title={t("notFound")}>{t("notFoundText")}</EmptyState>
        ) : match ? (
          <section aria-label={match.full_name} className="space-y-4">
            <PlayerCard
              size="sm"
              as="div"
              data={{ kuid: match.kuid, fullName: match.full_name, position: match.position, lgaName: match.lga_name, stateName: "", year: 0, verified: match.verified }}
              labels={{ idLabel: tu("idLabel"), verified: tu("verified"), photoAlt: "", noPhoto: tu("noPhoto") }}
            />
            {match.state === "on_roster" ? (
              <Notice signal="whistle" title={t("onRoster")} />
            ) : match.state === "invited" ? (
              <Notice signal="whistle" title={t("alreadyInvited")} />
            ) : (
              <form action={inviteAction} className="space-y-3">
                <input type="hidden" name="club" value={id} />
                <input type="hidden" name="kuid" value={match.kuid} />
                {match.current_club ? <Notice signal="yellow" title={t("atClub", { club: match.current_club })} /> : null}
                <SubmitButton pendingLabel={t("sending")} icon={<IconSend size={20} aria-hidden="true" />}>{t("send")}</SubmitButton>
                <p className="text-xs text-muted">{t("mustAccept")}</p>
              </form>
            )}
          </section>
        ) : null}
      </div>
    </AthleteShell>
  );
}

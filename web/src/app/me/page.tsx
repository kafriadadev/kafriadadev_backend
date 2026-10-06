import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import {
  IconChevronRight, IconCreditCard, IconIdBadge2, IconLogout, IconQrcode, IconShieldCheck, IconShirtSport, IconUser,
  IconUsersGroup,
} from "@/components/icons";
import { AthleteShell } from "@/components/ui/AthleteShell";
import { Button } from "@/components/ui/Button";
import { Notice, type Signal } from "@/components/ui/Notice";
import { PageHead } from "@/components/ui/Page";
import { Pill } from "@/components/ui/Pill";
import { PlayerCard } from "@/components/ui/PlayerCard";
import { SubmitButton } from "@/components/ui/SubmitButton";
import {
  ApiError, getMe, getMyClubs, getProfile, getVerification, type Me, type MyClubs, type PublicProfile, type Verification,
  type VerificationState,
} from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";
import { signOutAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("me"))("title") };
}
export const dynamic = "force-dynamic";

const SIGNAL: Record<VerificationState, Signal> = {
  none: "whistle", draft: "whistle", under_review: "var", approved: "done", rejected: "yellow", escalated: "flag", revoked: "whistle",
};

/**
 * My account (ATH-01): who they are, where their verification stands, their
 * card, and the way into everything else. Staff and club officials see their
 * work areas here too. Everything is a link or a form.
 */
export default async function MePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const t = await getTranslations("me");
  const tu = await getTranslations("ui");
  const welcome = Boolean((await searchParams).welcome);
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let me: Me;
  try {
    me = await getMe(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }

  let profile: PublicProfile | null = null;
  let verification: Verification | null = null;
  let clubs: MyClubs | null = null;
  if (me.kuid) {
    [profile, verification, clubs] = await Promise.all([
      getProfile(me.kuid).catch(() => null),
      getVerification(token).catch(() => null),
      getMyClubs(token).catch(() => null),
    ]);
  }

  const staffRoles = me.roles.filter((r) => r.role !== "athlete");
  const isAdmin = staffRoles.some((r) => r.role === "super_admin");
  const isCoordinator = staffRoles.some((r) => r.role === "lga_coordinator" || r.role === "state_coordinator");
  const clubGrants = me.roles.filter((r) => r.role === "club_admin" && r.scope_id);
  const roleNames = t.raw("roleNames") as Record<string, string>;
  const k = me.kuid ? encodeURIComponent(me.kuid) : null;
  const state = verification?.state ?? null;
  const invitations = clubs?.invitations.length ?? 0;

  const statusAction: Partial<Record<VerificationState, string>> = {
    none: t("status.noneAction"), draft: t("status.draftAction"), rejected: t("status.rejectedAction"), revoked: t("status.revokedAction"),
  };

  return (
    <AthleteShell current="home" kuid={me.kuid}>
      <PageHead eyebrow={t("eyebrow")} title={me.full_name} />

      {welcome ? <Notice signal="done" title={t("welcome")} className="mb-6"><p>{t("welcomeText")}</p></Notice> : null}

      {profile && k ? (
        <div className="mb-6 grid items-start gap-6 sm:grid-cols-[minmax(0,18rem)_1fr]">
          <PlayerCard
            data={{
              kuid: profile.kuid, fullName: profile.full_name, position: profile.playing_position, lgaName: profile.lga_name,
              stateName: profile.state_name, year: profile.registered_year, verified: profile.is_verified,
              photoSrc: profile.is_verified && profile.photo_url ? `/photo/${k}` : null,
            }}
            labels={{ idLabel: tu("idLabel"), verified: tu("verified"), photoAlt: tu("photoAlt", { name: profile.full_name }), noPhoto: tu("noPhoto") }}
          />
          <div className="space-y-3">
            {state ? (
              <Notice
                signal={SIGNAL[state]}
                title={t(`status.${state}`)}
                action={statusAction[state] ? <Button href="/verify" variant={state === "none" ? "primary" : "secondary"}>{statusAction[state]}</Button> : undefined}
              >
                <p>{t(`status.${state}Text`, { price: formatNaira(verification?.price_kobo ?? 250000) })}</p>
              </Notice>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button href={`/card/${k}`} variant="secondary" icon={<IconQrcode size={20} aria-hidden="true" />}>{t("card")}</Button>
              <Button href={`/a/${k}`} variant="ghost">{t("profile")}</Button>
            </div>
          </div>
        </div>
      ) : null}

      <nav aria-label={t("title")}>
        <ul className="divide-y divide-line overflow-hidden rounded-card border border-line">
          {k ? (
            <>
              <Row href="/clubs" icon={<IconShirtSport aria-hidden="true" />} title={t("clubs")} text={t("clubsText")}
                badge={invitations ? <Pill tone="warn">{t("invitations", { count: invitations })}</Pill> : null} />
              <Row href="/details" icon={<IconUser aria-hidden="true" />} title={t("details")} text={t("detailsText")} />
              <Row href="/payments" icon={<IconCreditCard aria-hidden="true" />} title={t("payments")} text={t("paymentsText")} />
            </>
          ) : null}
          {isAdmin ? <Row href="/admin" icon={<IconShieldCheck aria-hidden="true" />} title={t("admin")} text={t("adminText")} /> : null}
          {isCoordinator ? <Row href="/coordinator" icon={<IconUsersGroup aria-hidden="true" />} title={t("coordinator")} text={t("coordinatorText")} /> : null}
          {isAdmin || isCoordinator ? <Row href="/clubs/new" icon={<IconShirtSport aria-hidden="true" />} title={t("clubNew")} text={t("clubNewText")} /> : null}
          {clubGrants.map((r) => (
            <Row key={r.grant_id} href={`/clubs/${encodeURIComponent(r.scope_id as string)}`} icon={<IconIdBadge2 aria-hidden="true" />}
              title={r.scope_name ?? roleNames.club_admin} text={t("clubAdmin")} />
          ))}
        </ul>
      </nav>

      <section aria-labelledby="acct" className="mt-8 rounded-card bg-surface p-4">
        <h2 id="acct" className="text-lg uppercase">{t("account")}</h2>
        <dl className="mt-3 grid gap-3 sm:grid-cols-2">
          <div><dt className="text-xs font-bold uppercase tracking-[0.1em] text-muted">{t("phone")}</dt><dd className="font-mono">{me.phone}</dd></div>
          {me.lga_name ? <div><dt className="text-xs font-bold uppercase tracking-[0.1em] text-muted">{t("lga")}</dt><dd>{me.lga_name}</dd></div> : null}
        </dl>
        {staffRoles.length ? (
          <div className="mt-4">
            <p className="font-bold">{t("roles")}</p>
            <ul className="mt-1 list-disc pl-5">
              {staffRoles.map((r) => (
                <li key={r.grant_id}>{roleNames[r.role] ?? r.role}{r.scope_kind !== "global" ? ` · ${r.scope_name ?? r.scope_id}` : ""}</li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-muted">{t("staffTimeout")}</p>
          </div>
        ) : null}
        <form action={signOutAction} className="mt-4">
          <SubmitButton variant="secondary" size="md" block={false} pendingLabel={t("signingOut")} icon={<IconLogout size={20} aria-hidden="true" />}>
            {t("signOut")}
          </SubmitButton>
        </form>
      </section>
    </AthleteShell>
  );
}

function Row({ href, icon, title, text, badge }: { href: string; icon: React.ReactNode; title: string; text: string; badge?: React.ReactNode }) {
  return (
    <li>
      <a href={href} className="flex min-h-16 items-center gap-3 px-4 py-3 text-text no-underline hover:bg-surface">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-surface-2">{icon}</span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2 font-bold">{title}{badge}</span>
          <span className="block text-xs text-muted">{text}</span>
        </span>
        <IconChevronRight size={20} className="shrink-0 text-muted" aria-hidden="true" />
      </a>
    </li>
  );
}

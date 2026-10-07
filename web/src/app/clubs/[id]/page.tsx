import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconPosition, IconShieldCheck, IconShirtSport, IconUserPlus } from "@/components/icons";
import { KitRail, RaisedFlag } from "@/components/illustrations";
import { Iso } from "@/components/iso/Iso";
import { squadBench } from "@/components/iso/scenes";
import { AthleteShell } from "@/components/ui/AthleteShell";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { PageHead } from "@/components/ui/Page";
import { EmptyState, PageState } from "@/components/ui/PageState";
import { Pill } from "@/components/ui/Pill";
import { Scoreboard } from "@/components/ui/Scoreboard";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { Tabs } from "@/components/ui/Tabs";
import { ApiError, getClub, getMe, getClubVerification, type ClubDashboard, type ClubRosterRow } from "@/lib/api";
import { AGE_GROUPS, CATEGORIES, CLUB_LEVELS, CLUB_TYPES } from "@/lib/clubProfile";
import { formatNaira } from "@/lib/money";
import { positionUnit } from "@/lib/positions";
import { sessionToken } from "@/lib/session";
import { removeAction } from "./actions";
import { CountUp } from "@/components/ui/CountUp";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("club"))("tabs.roster") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
type T = Awaited<ReturnType<typeof getTranslations<"club">>>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));
const TABS = ["roster", "invitations", "details"] as const;

/**
 * A club's dashboard (CLB-02): the numbers, the squad, invitations, the
 * record. Which club a person may open is the API's decision from their own
 * grants; this screen shows what the API returns for the id in the address.
 */
export default async function ClubPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Search> }) {
  const t = await getTranslations("club");
  const { id } = await params;
  const query = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let club: ClubDashboard;
  let kuid: string | null = null;
  try {
    [club, kuid] = await Promise.all([getClub(token, id), getMe(token).then((m) => m.kuid)]);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403 || error.status === 404) {
        return (
          <PageState art={<RaisedFlag />} title={t("noAccessTitle")} action={<Button href="/me" size="lg" block>{t("back")}</Button>}>
            {t("noAccess")}
          </PageState>
        );
      }
    }
    throw error;
  }
  const price = club.verified ? null : await getClubVerification(token, id).then((v) => v.price_kobo).catch(() => null);

  const tab = TABS.find((k) => k === one(query.tab)) ?? "roster";
  const base = `/clubs/${encodeURIComponent(club.club_id)}`;
  const players = club.roster.filter((r) => r.state !== "invited");
  const invited = club.roster.filter((r) => r.state === "invited");
  const approved = club.status === "approved";
  const flash = (key: string, signal: "done" | "red", title: string, text: string) =>
    one(query[key]) ? <Notice signal={signal} title={title}><p>{key === "error" ? one(query.error) : text}</p></Notice> : null;

  return (
    <AthleteShell current="clubs" kuid={kuid}>
      <PageHead back={{ href: "/me", label: t("back") }} eyebrow={t("eyebrow", { sport: club.sport, lga: club.lga_name })} title={club.name} />

      <div className="mb-6 space-y-3 empty:hidden">
        {flash("registered", "done", t("registered"), t("registeredText"))}
        {flash("invited", "done", t("invited"), t("invitedText"))}
        {flash("saved", "done", t("saved"), t("savedText"))}
        {flash("removed", "done", t("removed"), t("removedText"))}
        {flash("error", "red", t("error"), "")}
        {club.status === "pending_review" || club.status === "unconfirmed" ? (
          <Notice signal="var" title={t("pending")}><p>{t("pendingText")}</p></Notice>
        ) : club.status === "suspended" ? (
          <Notice signal="flag" title={t("suspended")}><p>{t("suspendedText")}</p></Notice>
        ) : null}
      </div>

      <Scoreboard
        items={[
          { label: t("stats.players"), value: <CountUp value={club.players} /> },
          { label: t("stats.verified"), value: <CountUp value={club.verified_players} />, accent: true },
          { label: t("stats.invites"), value: <CountUp value={club.invites_out} /> },
        ]}
      />

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-card border border-line p-4">
        {club.verified ? (
          <Pill tone="good" icon={<IconShieldCheck size={16} aria-hidden="true" />}>{t("verified")}</Pill>
        ) : (
          <>
            <div>
              <p className="font-bold">{t("notVerified")}</p>
              {price ? <p className="text-xs text-muted">{t("notVerifiedText", { price: formatNaira(price) })}</p> : null}
            </div>
            {approved ? <Button href={`${base}/verify`} variant="secondary" icon={<IconShieldCheck size={20} aria-hidden="true" />}>{t("verify")}</Button> : null}
          </>
        )}
      </div>

      <div className="mt-8 flex flex-wrap items-end justify-between gap-3">
        <Tabs
          className="flex-1"
          label={t("tabsLabel")}
          current={`${base}?tab=${tab}`}
          items={TABS.map((k) => ({
            href: `${base}?tab=${k}`,
            label: t(`tabs.${k}`),
            count: k === "roster" ? players.length : k === "invitations" ? invited.length : undefined,
          }))}
        />
        {approved ? <Button href={`${base}/invite`} icon={<IconUserPlus size={20} aria-hidden="true" />}>{t("addPlayer")}</Button> : null}
      </div>

      <div className="mt-6">
        {tab === "roster" ? (
          players.length ? (
            <>
              <Iso fig={squadBench(players.length)} name="bench" className="mx-auto mb-4 max-w-md" />
              <Squad t={t} rows={players} clubId={club.club_id} tab="roster" action={t("remove")} />
            </>
          ) : (
            <EmptyState wideArt art={<Iso fig={squadBench(0)} name="bench" />} title={t("noPlayers")}
              action={approved ? <Button href={`${base}/invite`} icon={<IconUserPlus size={20} aria-hidden="true" />}>{t("addPlayer")}</Button> : undefined}>
              {t("noPlayersText")}
            </EmptyState>
          )
        ) : null}
        {tab === "invitations" ? (
          invited.length ? (
            <Squad t={t} rows={invited} clubId={club.club_id} tab="invitations" action={t("withdraw")} />
          ) : (
            <EmptyState art={<KitRail />} title={t("noInvites")}>{t("noInvitesText")}</EmptyState>
          )
        ) : null}
        {tab === "details" ? <Details t={t} club={club} base={base} /> : null}
      </div>
    </AthleteShell>
  );
}

/** The squad as a squad: shirt, name, ID, status, one action each. */
function Squad({ t, rows, clubId, tab, action }: { t: T; rows: ClubRosterRow[]; clubId: string; tab: string; action: string }) {
  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {rows.map((r) => {
        const unit = positionUnit(r.position);
        return (
          <li key={r.roster_id} className="flex flex-col gap-3 rounded-card bg-plate-bg p-3 text-plate-ink shadow-lift ring-1 ring-[color-mix(in_srgb,var(--plate-ink)_10%,transparent)]">
            <div className="flex items-start gap-3">
              <span className="grid size-12 shrink-0 place-items-center rounded-input bg-plate-accent text-boot" aria-hidden="true">
                {unit ? <IconPosition position={unit} size={36} stroke={1.75} /> : <IconShirtSport size={28} />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-display text-lg font-extrabold uppercase italic leading-tight">{r.full_name}</p>
                {r.position ? <p className="text-xs text-plate-muted">{r.position}</p> : null}
                <p className="mt-0.5 whitespace-nowrap font-mono text-xs scoreboard-digits">{r.kuid}</p>
              </div>
            </div>
            <div className="flex items-center justify-between gap-2">
              <Pill tone={r.state === "verified" ? "good" : r.state === "invited" ? "check" : "neutral"}
                icon={r.state === "verified" ? <IconShieldCheck size={16} aria-hidden="true" /> : undefined}>
                {t(`state.${r.state}`)}
              </Pill>
              <form action={removeAction}>
                <input type="hidden" name="club" value={clubId} />
                <input type="hidden" name="roster" value={r.roster_id} />
                <input type="hidden" name="tab" value={tab} />
                <SubmitButton variant="ghost" size="md" block={false} pendingLabel={t("updating")}>{action}</SubmitButton>
              </form>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function Details({ t, club, base }: { t: T; club: ClubDashboard; base: string }) {
  const p = (club.profile ?? {}) as Record<string, unknown>;
  const s = (v: unknown): string | null => (v === null || v === undefined || v === "" ? null : String(v));
  const label = (map: Record<string, string>, v: unknown) => (s(v) ? (map[String(v)] ?? String(v)) : null);
  const groups = Array.isArray(p.age_groups) ? (p.age_groups as string[]).map((g) => AGE_GROUPS[g] ?? g).join(", ") : null;
  const rows: [string, string | null][] = [
    [t("fields.name"), club.name],
    [t("fields.short"), s(p.short_name)],
    [t("fields.kind"), label(CLUB_TYPES, p.type)],
    [t("fields.sport"), club.sport],
    [t("fields.category"), label(CATEGORIES, p.category)],
    [t("fields.ages"), groups],
    [t("fields.level"), label(CLUB_LEVELS, p.level)],
    [t("fields.founded"), club.year_founded ? String(club.year_founded) : null],
    [t("fields.ground"), [s(p.ground_name), s(p.ground_address), s(p.town)].filter(Boolean).join(", ") || null],
    [t("fields.area"), club.lga_name],
    [t("fields.phone"), club.contact_phone],
    [t("fields.email"), s(p.club_email)],
    [t("fields.cac"), s(p.cac_number)],
    [t("fields.affiliation"), s(p.affiliation)],
    [t("fields.colours"), s(p.colours)],
    [t("fields.website"), s(p.website)],
    [t("fields.rep"), s(p.rep_role)],
    [t("fields.second"), s(p.official2_name) ? `${s(p.official2_name)} (${s(p.official2_role) ?? ""}), ${s(p.official2_phone) ?? ""}` : null],
  ];
  const missing = rows.some(([, v]) => v === null);
  return (
    <section aria-label={t("tabs.details")} className="space-y-4">
      {missing ? <Notice signal="yellow" title={t("incomplete")}><p>{t("incompleteText")}</p></Notice> : null}
      <dl className="grid gap-px overflow-hidden rounded-card border border-line bg-line sm:grid-cols-2">
        {rows.map(([k, v]) => (
          <div key={k} className="bg-bg p-3">
            <dt className="text-xs font-bold uppercase tracking-widest text-muted">{k}</dt>
            <dd className={v ? "font-bold" : "text-muted"}>{v ?? t("notGiven")}</dd>
          </div>
        ))}
      </dl>
      <Button href={`${base}/edit`} variant="secondary">{t("edit")}</Button>
    </section>
  );
}

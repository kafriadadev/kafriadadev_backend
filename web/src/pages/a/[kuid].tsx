import type { GetServerSideProps } from "next";
import Head from "next/head";
import { createTranslator } from "next-intl";

import { IconArrowRight, IconInfoCircle, IconSearch, IconShieldCheck, IconShirtSport, IconUser } from "@/components/icons";
import { EmptyNet } from "@/components/illustrations";
import { Button } from "@/components/ui/Button";
import { WithKuids } from "@/components/ui/Kuid";
import { Footer, TopBar } from "@/components/ui/Navigation";
import { PageState } from "@/components/ui/PageState";
import { PlayerCard } from "@/components/ui/PlayerCard";
import { DEFAULT_LOCALE } from "@/i18n/request";
import { getProfile, type PublicProfile } from "@/lib/api";
import messages from "../../../messages/en.json";

/**
 * The public profile (PUB-01): where a scanned QR lands. The only screen a
 * stranger ever sees, on a cheap phone with one bar of signal. No account, no
 * cookie, and zero JavaScript: this page is on the Pages Router precisely so
 * it can switch the runtime off.
 *
 * The wording is load-bearing. A valid signature proves the QR came from us,
 * not that the bearer is the person named (a copied card keeps its
 * signature), so the pill says "Issued by" and the line beside it tells the
 * reader to check the face. An unsigned or bad signature still shows the full
 * record: someone typing an ID by hand must still see the athlete.
 */
// unstable_runtimeJS is read by next/dist/server/render.js; Next's generated
// type check does not list it, and `runtime` keeps that check satisfied.
export const config = { runtime: "nodejs", unstable_runtimeJS: false };

type Props = { profile: PublicProfile | null; origin: string };

export const getServerSideProps: GetServerSideProps<Props> = async ({ params, query, req, res }) => {
  const kuid = String(params?.kuid ?? "");
  const sig = typeof query.s === "string" ? query.s : undefined;
  const proto = (req.headers["x-forwarded-proto"] as string | undefined) ?? "http";
  const origin = `${proto}://${req.headers.host}`;
  let profile: PublicProfile | null = null;
  try {
    profile = await getProfile(kuid, sig);
  } catch {
    // A malformed ID and a missing one get the same answer, so nobody can walk
    // the register by guessing.
  }
  if (!profile) res.statusCode = 404;
  // Matches the 60-second edge cache the architecture assumes; the query string
  // (the signature) is part of the cache key.
  res.setHeader("Cache-Control", "public, s-maxage=60, stale-while-revalidate=300");
  return { props: { profile, origin } };
};

export default function ProfilePage({ profile, origin }: Props) {
  const t = createTranslator({ locale: DEFAULT_LOCALE, messages });
  const nav = {
    homeLabel: t("brand.home"),
    links: [
      { href: "/find", label: t("nav.findId"), icon: <IconSearch size={20} aria-hidden="true" /> },
      { href: "/clubs/register", label: t("nav.registerClub"), icon: <IconShirtSport size={20} aria-hidden="true" /> },
      { href: "/me", label: t("nav.myAccount"), icon: <IconUser size={20} aria-hidden="true" /> },
    ],
    action: { href: "/register", label: t("nav.registerFree") },
    menu: { label: t("nav.menu"), title: t("nav.menuTitle"), close: t("nav.close") },
  };
  const footer = (
    <Footer
      tagline={t("brand.tagline")}
      label={t("nav.footer")}
      links={[
        { href: "/find", label: t("nav.findId") },
        { href: "/register", label: t("nav.registerAthlete") },
        { href: "/clubs/register", label: t("nav.registerClub") },
        { href: "/privacy", label: t("nav.privacy") },
      ]}
    />
  );

  if (!profile) {
    return (
      <>
        <Head>
          <title>{`${t("profile.notFoundTitle")} · KAFRIADA NET`}</title>
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <meta name="robots" content="noindex" />
        </Head>
        <TopBar {...nav} />
        <main id="main">
          <PageState
            art={<EmptyNet />}
            title={t("profile.notFoundTitle")}
            action={<Button href="/find" size="lg" block icon={<IconSearch size={20} aria-hidden="true" />}>{t("profile.notFoundAction")}</Button>}
            secondary={<a href="/">{t("profile.home")}</a>}
          >
            <WithKuids text={t("profile.notFoundText")} />
          </PageState>
        </main>
        {footer}
      </>
    );
  }

  const p = profile;
  const k = encodeURIComponent(p.kuid);
  const details = [p.playing_position, p.lga_name, p.state_name].filter(Boolean).join(", ");
  const description = t("profile.metaDescription", { name: p.full_name, details, year: p.registered_year });
  const title = `${p.full_name} · ${p.kuid}`;
  const identity = p.is_verified ? t("profile.checked") : p.verification_withdrawn ? t("profile.withdrawn") : t("profile.notChecked");

  return (
    <>
      <Head>
        <title>{`${title} · KAFRIADA NET`}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="description" content={description} />
        {/* The WhatsApp preview: the player card, drawn on the server. */}
        <meta property="og:type" content="profile" />
        <meta property="og:site_name" content="KAFRIADA NET" />
        <meta property="og:title" content={p.full_name} />
        <meta property="og:description" content={description} />
        <meta property="og:url" content={`${origin}/a/${k}`} />
        <meta property="og:image" content={`${origin}/og/${k}`} />
        <meta property="og:image:width" content="1200" />
        <meta property="og:image:height" content="630" />
        <meta name="twitter:card" content="summary_large_image" />
      </Head>
      <TopBar {...nav} />
      <main id="main" className="mx-auto w-full max-w-measure px-4 pb-16 pt-6 sm:px-6">
        <div className="mx-auto max-w-sm">
          <PlayerCard
            size="lg"
            nameAs="h1"
            data={{
              kuid: p.kuid,
              fullName: p.full_name,
              position: p.playing_position,
              lgaName: p.lga_name,
              stateName: p.state_name,
              year: p.registered_year,
              verified: p.is_verified,
              photoSrc: p.is_verified && p.photo_url ? `/photo/${k}` : null,
            }}
            labels={{ idLabel: t("ui.idLabel"), verified: t("ui.verified"), photoAlt: t("ui.photoAlt", { name: p.full_name }), noPhoto: t("ui.noPhoto") }}
          />

          {/* Directly under the photo: is this real, and is this the person? */}
          {p.issued_by_kafriada ? (
            <div role="status" className="mt-4 rounded-card border-2 border-check bg-check-bg p-4">
              <p className="flex items-center gap-2 font-bold text-check">
                <IconShieldCheck aria-hidden="true" />
                {t("profile.issued")}
              </p>
              <p className="mt-1">{t("profile.issuedText")}</p>
            </div>
          ) : (
            <div role="status" className="mt-4 rounded-card border-2 border-line bg-surface p-4">
              <p className="flex items-center gap-2 font-bold">
                <IconInfoCircle aria-hidden="true" />
                {t("profile.unsigned")}
              </p>
              <p className="mt-1 text-muted">{t("profile.unsignedText")}</p>
            </div>
          )}
        </div>

        <section aria-labelledby="facts" className="mx-auto mt-8 max-w-sm">
          <h2 id="facts" className="sr-only">{t("profile.facts")}</h2>
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-card border border-line bg-line">
            {[
              [t("profile.age"), String(p.age)],
              [t("profile.since"), String(p.registered_year)],
              [t("profile.registered"), `${p.lga_name}, ${p.state_name}`],
              [t("profile.identity"), identity],
            ].map(([label, value]) => (
              <div key={label} className="bg-bg p-3">
                <dt className="text-xs font-bold uppercase tracking-[0.1em] text-muted">{label}</dt>
                <dd className="mt-1 font-bold">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-6 text-xs text-muted">{t("profile.privacy")}</p>
          <div className="mt-8">
            <Button href="/register" size="lg" block iconAfter={<IconArrowRight size={20} aria-hidden="true" />}>{t("profile.cta")}</Button>
          </div>
        </section>
      </main>
      {footer}
    </>
  );
}

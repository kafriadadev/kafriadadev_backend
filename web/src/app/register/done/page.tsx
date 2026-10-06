import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { IconArrowRight, IconBrandWhatsapp, IconCheck, IconDownload, IconPrinter, IconShieldCheck } from "@/components/icons";
import { Button } from "@/components/ui/Button";
import { Confetti } from "@/components/ui/Confetti";
import { FlowSteps } from "@/components/ui/FlowSteps";
import { Page } from "@/components/ui/Page";
import { PlayerCard } from "@/components/ui/PlayerCard";
import { ApiError, getMe, getProfile } from "@/lib/api";
import { sessionToken } from "@/lib/session";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("done"))("eyebrow"), robots: { index: false } };
}
export const dynamic = "force-dynamic";

/**
 * Your ID is ready (AUT-03): the conversion moment. The free thing is handed
 * over first; the optional ₦2,500 step appears only below it, as an
 * invitation. This screen cannot fail: by now the KUID is committed.
 */
export default async function DonePage() {
  const t = await getTranslations("done");
  const tu = await getTranslations("ui");
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let me;
  try {
    me = await getMe(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }
  // Club representatives and staff have no athlete ID to hand over.
  if (!me.kuid) redirect("/me?welcome=1");
  const profile = await getProfile(me.kuid);

  const h = await headers();
  const origin = `${h.get("x-forwarded-proto") ?? "http"}://${h.get("host")}`;
  const profileUrl = `${origin}/a/${encodeURIComponent(profile.kuid)}`;
  const share = `https://wa.me/?text=${encodeURIComponent(t("shareText", { url: profileUrl }))}`;
  const first = profile.full_name.split(" ")[0];
  const k = encodeURIComponent(profile.kuid);

  return (
    <Page>
      <FlowSteps current={2} />
      <p className="inline-flex items-center gap-2 rounded-pill bg-pitch px-3 py-1 text-xs font-bold uppercase tracking-[0.14em] text-on-pitch motion-rise">
        <IconCheck size={16} stroke={3} aria-hidden="true" />
        {t("eyebrow")}
      </p>
      <h1 className="mt-3 motion-rise">{t("title", { name: first })}</h1>
      <p className="mt-2 text-md text-muted">{t("permanent")}</p>

      {/* The reveal: the card lifts into place. */}
      <div className="my-8 flex justify-center [perspective:900px]">
        <div className="relative w-full max-w-xs animate-[kaf-reveal_var(--dur-show)_var(--ease-bounce)_both]">
          <span
            className="absolute -right-3 top-24 z-10 rounded-input border-4 border-kit-red bg-plate-bg px-3 py-1 font-display text-2xl font-extrabold uppercase italic text-[var(--card-red)] shadow-lift animate-[kaf-stamp_var(--dur-move)_var(--ease-bounce)_480ms_both]"
            aria-hidden="true"
          >
            {t("stamp")}
          </span>
          <PlayerCard
            size="lg"
            data={{
              kuid: profile.kuid,
              fullName: profile.full_name,
              position: profile.playing_position,
              lgaName: profile.lga_name,
              stateName: profile.state_name,
              year: profile.registered_year,
              verified: profile.is_verified,
              photoSrc: profile.is_verified && profile.photo_url ? `/photo/${k}` : null,
            }}
            labels={{ idLabel: tu("idLabel"), verified: tu("verified"), photoAlt: tu("photoAlt", { name: profile.full_name }), noPhoto: tu("noPhoto") }}
          />
        </div>
      </div>

      <Confetti />
      <div className="grid gap-3">
        <Button href={share} size="lg" block icon={<IconBrandWhatsapp size={22} aria-hidden="true" />}>{t("share")}</Button>
        <div className="grid gap-3 sm:grid-cols-2">
          <Button href={`/card/${k}/card.png`} variant="secondary" size="lg" block icon={<IconDownload size={20} aria-hidden="true" />} download>
            {t("download")}
          </Button>
          <Button href={`/card/${k}`} variant="secondary" size="lg" block icon={<IconPrinter size={20} aria-hidden="true" />}>{t("print")}</Button>
        </div>
        <p className="text-center"><a href={`/a/${k}`}>{t("profile")}</a></p>
      </div>

      {/* After the free thing, never before it. */}
      <section aria-labelledby="next" className="mt-12 rounded-card border-2 border-dashed border-line-strong p-5">
        <h2 id="next" className="flex items-center gap-2 text-lg uppercase">
          <IconShieldCheck aria-hidden="true" />
          {t("nextTitle")}
        </h2>
        <p className="mt-2 text-muted">{t("nextText")}</p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Button href="/verify" variant="secondary" iconAfter={<IconArrowRight size={20} aria-hidden="true" />}>{t("nextAction")}</Button>
          <Button href="/me" variant="ghost">{t("account")}</Button>
        </div>
      </section>
    </Page>
  );
}

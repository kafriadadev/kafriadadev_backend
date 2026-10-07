import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import { IconArrowRight, IconDownload, IconPrinter, IconShieldCheck } from "@/components/icons";
import { Button } from "@/components/ui/Button";
import { Page, PageHead } from "@/components/ui/Page";
import { PlayerCard, PrintCard } from "@/components/ui/PlayerCard";
import { KuidStrip } from "@/components/ui/Scoreboard";
import { getProfile, type PublicProfile } from "@/lib/api";
import { Tilt } from "@/components/ui/Tilt";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("cardPage"))("title"), robots: { index: false } };
}
export const dynamic = "force-dynamic";

/**
 * The card (AUT-03 print, ATH-03). The page is the print layout: the browser's
 * own Print command produces the card at ID-1 size, which works where scripts
 * do not. PNG and PDF are plain downloads for browsers without "print to PDF".
 * The free thing comes first; the optional verification only after it.
 */
export default async function CardPage({ params }: { params: Promise<{ kuid: string }> }) {
  const { kuid } = await params;
  const t = await getTranslations("cardPage");
  const tu = await getTranslations();

  let profile: PublicProfile;
  try {
    profile = await getProfile(kuid);
  } catch {
    notFound();
  }
  const k = encodeURIComponent(profile.kuid);
  const card = {
    kuid: profile.kuid,
    fullName: profile.full_name,
    position: profile.playing_position,
    lgaName: profile.lga_name,
    stateName: profile.state_name,
    year: profile.registered_year,
    verified: profile.is_verified,
    photoSrc: profile.is_verified && profile.photo_url ? `/photo/${k}` : null,
  };
  const labels = { idLabel: tu("ui.idLabel"), verified: tu("ui.verified"), photoAlt: tu("ui.photoAlt", { name: profile.full_name }), noPhoto: tu("ui.noPhoto") };

  return (
    <Page>
      <div className="print:hidden">
        <PageHead eyebrow={t("eyebrow")} title={t("heading", { name: profile.full_name.split(" ")[0] })} lede={t("lede")} />
      </div>

      {/* On screen: the player card and its code. On paper: the ID-1 card. */}
      <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start sm:justify-center print:hidden">
        <div className="w-full max-w-xs">
          <Tilt><PlayerCard size="lg" data={card} labels={labels} /></Tilt>
        </div>
        <figure className="flex flex-col items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`/qr/${k}`} alt={tu("card.scanHelp")} width={176} height={176} className="rounded-card bg-plate-bg p-2" />
          <figcaption className="font-display text-lg font-extrabold uppercase italic">{tu("card.scan")}</figcaption>
        </figure>
      </div>
      <div className="hidden print:block">
        <PrintCard
          data={card}
          labels={labels}
          qrSrc={`/qr/${k}`}
          back={{ scan: tu("card.scan"), scanHelp: tu("card.scanHelp"), issuedBy: tu("card.issuedBy") }}
        />
      </div>

      <div className="mt-8 space-y-6 print:hidden">
        <div className="grid gap-3 sm:grid-cols-2">
          <Button href={`/card/${k}/card.png`} size="lg" block download icon={<IconDownload size={20} aria-hidden="true" />}>{t("png")}</Button>
          <Button href={`/card/${k}/card.pdf`} variant="secondary" size="lg" block download icon={<IconDownload size={20} aria-hidden="true" />}>{t("pdf")}</Button>
        </div>
        <div className="flex gap-3 rounded-card bg-surface p-4">
          <IconPrinter className="shrink-0" aria-hidden="true" />
          <div>
            <p className="font-bold">{t("print")}</p>
            <p className="text-muted">{t("printText")}</p>
          </div>
        </div>
        <div>
          <p className="mb-2 font-bold">{t("keep")}</p>
          <KuidStrip kuid={profile.kuid} />
          <p className="mt-2 text-xs text-muted">{t("keepText")}</p>
        </div>
        <p><a href={`/a/${k}`}>{t("profile")}</a></p>

        {profile.is_verified ? null : (
          <section aria-labelledby="verify" className="rounded-card border-2 border-dashed border-line-strong p-5">
            <h2 id="verify" className="flex items-center gap-2 text-lg uppercase"><IconShieldCheck aria-hidden="true" /> {t("verifyTitle")}</h2>
            <p className="mt-2 text-muted">{t("verifyText")}</p>
            <Button href="/verify" variant="secondary" className="mt-4" iconAfter={<IconArrowRight size={20} aria-hidden="true" />}>{t("verifyAction")}</Button>
          </section>
        )}
      </div>
    </Page>
  );
}

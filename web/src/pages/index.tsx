import type { GetServerSideProps } from "next";

import { PublicDocument, translator } from "@/components/PublicDocument";
import { IconArrowRight, IconCash, IconCreditCard, IconMapPin, IconQrcode, IconSearch, IconShirtSport, IconUser } from "@/components/icons";
import { CentreCircle } from "@/components/pitch/PitchLines";
import { Button } from "@/components/ui/Button";
import { WithKuids } from "@/components/ui/Kuid";
import { PlayerCard } from "@/components/ui/PlayerCard";
import { Scoreboard } from "@/components/ui/Scoreboard";
import { listLgas, type Lga } from "@/lib/api";

/**
 * The landing page (PUB-02). Most people arrive from a poster or a WhatsApp
 * forward, not a search. It answers what this is, what it costs and how to
 * start, then gets out of the way. Free comes first; the price appears only
 * as an optional, later step. Zero JavaScript.
 */
export const config = { runtime: "nodejs", unstable_runtimeJS: false };

type Props = { open: Lga[] };

// Which LGAs are open changes as waves roll out; five minutes is fresh enough,
// and it spares the busiest page a call to the API on every visit.
const FRESH_MS = 5 * 60 * 1000;
let cached: { open: Lga[]; at: number } | null = null;

export const getServerSideProps: GetServerSideProps<Props> = async ({ res }) => {
  if (!cached || Date.now() - cached.at >= FRESH_MS) {
    try {
      cached = { open: (await listLgas()).filter((l) => l.is_open), at: Date.now() };
    } catch {
      // The page works without the list (or with the last one); it is a nicety.
    }
  }
  const open = cached?.open ?? [];
  res.setHeader("Cache-Control", "public, s-maxage=300, stale-while-revalidate=600");
  return { props: { open } };
};

export default function Home({ open }: Props) {
  const t = translator();
  const how = t.raw("home.how") as { title: string; text: string }[];
  const howIcons = [<IconUser key="u" />, <IconShirtSport key="s" />, <IconQrcode key="q" />];

  return (
    <PublicDocument>
      {/* Kick-off: the centre circle chalks itself in, the card lifts and settles. */}
      <section className="relative overflow-hidden border-b border-line bg-surface">
        {/* A fixed size anchored to the top: sized from the section, it moved when the fonts arrived. */}
        <CentreCircle draw className="pointer-events-none absolute -right-24 -top-20 size-[40rem] opacity-40 md:right-[8%]" />
        <div className="relative mx-auto grid max-w-wide items-center gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1.2fr_1fr] md:py-20">
          <div>
            <p className="inline-flex items-center gap-2 rounded-pill bg-bg px-3 py-1 text-xs font-bold uppercase tracking-[0.14em] text-link">
              <IconMapPin size={16} aria-hidden="true" />
              {t("home.eyebrow")}
            </p>
            <h1 className="mt-4 text-4xl motion-rise">{t("home.title")}</h1>
            <p className="mt-4 max-w-xl text-md text-muted">{t("home.lede")}</p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
              <Button href="/register" size="lg" iconAfter={<IconArrowRight size={20} aria-hidden="true" />}>
                {t("home.register")}
              </Button>
              <Button href="/find" variant="secondary" size="lg" icon={<IconSearch size={20} aria-hidden="true" />}>
                {t("home.find")}
              </Button>
            </div>
            <p className="mt-3 text-xs text-muted">{t("home.free")}</p>
          </div>
          <div className="relative mx-auto w-full max-w-xs motion-rise [animation-delay:120ms]">
            {/* Filled by /delight.js on a capable device: the runner, leaning towards the pointer. */}
            <div data-figure-slot="hero" className="pointer-events-none absolute -left-40 -top-12 -z-10 hidden w-72 text-text opacity-80 lg:block" aria-hidden="true" />
            <p className="sr-only">{t("home.sampleLabel")}</p>
            <PlayerCard
              as="div"
              size="lg"
              nameAs="p"
              data={{
                kuid: "KA-NG-JG-BKD-2026-000123",
                fullName: "Aisha Musa",
                position: "Striker",
                lgaName: "Birnin Kudu",
                stateName: "Jigawa",
                year: 2026,
                verified: false,
              }}
              labels={{ idLabel: t("ui.idLabel"), verified: t("ui.verified"), photoAlt: "", noPhoto: t("ui.noPhoto") }}
            />
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-wide space-y-16 px-4 py-14 sm:px-6">
        <Scoreboard
          items={[
            { label: t("home.facts.cost"), value: t("home.facts.costValue"), accent: true },
            { label: t("home.facts.time"), value: t("home.facts.timeValue") },
            { label: t("home.facts.life"), value: t("home.facts.lifeValue") },
          ]}
        />

        <section aria-labelledby="how">
          <h2 id="how" className="text-2xl uppercase">{t("home.howTitle")}</h2>
          <ol className="mt-6 grid gap-4 md:grid-cols-3">
            {how.map((step, i) => (
              <li key={step.title} className="touchline rounded-r-card bg-surface p-5">
                <p className="flex items-center gap-3">
                  <span className="grid size-10 place-items-center rounded-full bg-pitch text-on-pitch" aria-hidden="true">{howIcons[i]}</span>
                  <span className="font-display text-xl font-extrabold uppercase italic">
                    <span className="text-muted">{i + 1}.</span> {step.title}
                  </span>
                </p>
                <p className="mt-3 text-muted"><WithKuids text={step.text} /></p>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="open">
          <h2 id="open" className="text-2xl uppercase">{t("home.openTitle")}</h2>
          {open.length ? (
            <ul className="mt-4 flex flex-wrap gap-2">
              {open.map((l) => (
                <li key={l.id} className="inline-flex min-h-10 items-center gap-2 rounded-pill bg-check-bg px-4 font-bold text-check">
                  <span className="size-2 rounded-full bg-kit-red" aria-hidden="true" />
                  {l.name}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-muted">{t("home.openNone")}</p>
          )}
        </section>

        <div className="grid gap-4 md:grid-cols-2">
          <section aria-labelledby="verify" className="rounded-card border border-line p-6">
            <h2 id="verify" className="text-xl uppercase">{t("home.verifyTitle")}</h2>
            <p className="mt-3 text-muted">{t("home.verifyText")}</p>
            <p className="mt-4 flex gap-4 text-xs font-bold">
              <span className="inline-flex items-center gap-1.5"><IconCreditCard size={20} aria-hidden="true" /> {t("home.payCard")}</span>
              <span className="inline-flex items-center gap-1.5"><IconCash size={20} aria-hidden="true" /> {t("home.payCash")}</span>
            </p>
          </section>
          <section aria-labelledby="clubs" className="rounded-card border border-line p-6">
            <h2 id="clubs" className="text-xl uppercase">{t("home.clubsTitle")}</h2>
            <p className="mt-3 text-muted">{t("home.clubsText")}</p>
            <Button href="/clubs/register" variant="secondary" className="mt-4" icon={<IconShirtSport size={20} aria-hidden="true" />}>
              {t("home.clubsAction")}
            </Button>
          </section>
        </div>
      </div>

      {/* The one action, always in reach on a phone. */}
      <div className="sticky bottom-0 z-20 border-t border-line bg-bg p-3 sm:hidden">
        <Button href="/register" size="lg" block>{t("home.register")}</Button>
      </div>
      <script src="/delight.js" defer />
    </PublicDocument>
  );
}

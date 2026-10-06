import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";
import { styleguideEnabled as enabled } from "@/lib/styleguide";

import { Logo } from "@/components/brand/Logo";
import {
  IconAlertTriangle, IconBallFootball, IconBrandWhatsapp, IconCamera, IconCash, IconCheck,
  IconClock, IconCopy, IconCreditCard, IconDownload, IconFlag, IconHome, IconIdBadge2,
  IconInfoCircle, IconLock, IconMail, IconMapPin, IconPhone, IconPlayFootball, IconPosition,
  IconPrinter, IconQrcode, IconRedCard, IconScan, IconScoreboard, IconSearch, IconShare,
  IconShieldCheck, IconShirtSport, IconSoccerField, IconTrophy, IconUser, IconUsersGroup,
  IconVarScreen, IconWhistle, IconWifiOff, IconYellowCard,
} from "@/components/icons";
import { CentreCircle, HalfwayLine, PenaltyArc, Pitch } from "@/components/pitch/PitchLines";

export const metadata: Metadata = { title: "Style guide", robots: { index: false } };
export const dynamic = "force-dynamic";


const BRAND = [
  { token: "--pitch", hex: "#0EAD2C", swatch: "bg-pitch", note: "Logo green. Fills only: 2.99:1 on white. Boot text on it 6.48:1." },
  { token: "--pitch-ink", hex: "#087A1F", swatch: "bg-pitch-ink", note: "Green text and links on light. 5.51:1 on white." },
  { token: "--pitch-deep", hex: "#06661A", swatch: "bg-pitch-deep", note: "Pressed states, headers. 7.18:1 on white." },
  { token: "--kit-red", hex: "#EB0002", swatch: "bg-kit-red", note: "Logo red. Accents only. 4.63:1 on white." },
  { token: "--card-red", hex: "#C70003", swatch: "bg-[var(--card-red)]", note: "Errors, red-card state. 6.12:1 on white." },
  { token: "--yellow-card", hex: "#FFC21A", swatch: "bg-[var(--yellow-card)]", note: "Warning fills. Boot text on it 11.95:1." },
  { token: "--boot", hex: "#0A0F0B", swatch: "bg-boot", note: "Text, scoreboards. 19.34:1 on white." },
  { token: "--chalk", hex: "#FFFFFF", swatch: "bg-chalk", note: "Background, lines under floodlights." },
  { token: "--turf-50", hex: "#F6F8F3", swatch: "bg-[var(--turf-50)]", note: "Soft section background." },
  { token: "--night", hex: "#07110A", swatch: "bg-[var(--night)]", note: "Floodlit background. Logo green on it 6.43:1." },
] as const;

const ROLES = [
  { token: "--bg", swatch: "bg-bg" },
  { token: "--surface", swatch: "bg-surface" },
  { token: "--surface-2", swatch: "bg-surface-2" },
  { token: "--text", swatch: "bg-text" },
  { token: "--text-muted", swatch: "bg-muted" },
  { token: "--link", swatch: "bg-link" },
  { token: "--line-strong", swatch: "bg-line-strong" },
  { token: "--danger", swatch: "bg-danger" },
  { token: "--danger-bg", swatch: "bg-danger-bg" },
  { token: "--check", swatch: "bg-check" },
  { token: "--check-bg", swatch: "bg-check-bg" },
  { token: "--scoreboard", swatch: "bg-scoreboard" },
] as const;

const TYPE = [
  { token: "--text-4xl", cls: "text-4xl", px: "44 → 64" },
  { token: "--text-3xl", cls: "text-3xl", px: "36 → 48" },
  { token: "--text-2xl", cls: "text-2xl", px: "30 → 36" },
  { token: "--text-xl", cls: "text-xl", px: "24 → 28" },
  { token: "--text-lg", cls: "text-lg", px: "20 → 22" },
  { token: "--text-md", cls: "text-md", px: "18" },
  { token: "--text-base", cls: "text-base", px: "16, body, never smaller" },
  { token: "--text-xs", cls: "text-xs", px: "14, labels only" },
] as const;

const SPACE = [
  { n: 4, cls: "w-1" }, { n: 8, cls: "w-2" }, { n: 12, cls: "w-3" }, { n: 16, cls: "w-4" },
  { n: 24, cls: "w-6" }, { n: 32, cls: "w-8" }, { n: 48, cls: "w-12" }, { n: 64, cls: "w-16" },
] as const;

const ICONS = [
  ["ball-football", IconBallFootball], ["shirt-sport", IconShirtSport], ["soccer-field", IconSoccerField],
  ["play-football", IconPlayFootball], ["scoreboard", IconScoreboard], ["id-badge", IconIdBadge2],
  ["qrcode", IconQrcode], ["scan", IconScan], ["trophy", IconTrophy], ["cash", IconCash],
  ["credit-card", IconCreditCard], ["shield-check", IconShieldCheck], ["map-pin", IconMapPin],
  ["user", IconUser], ["users-group", IconUsersGroup], ["search", IconSearch], ["phone", IconPhone],
  ["mail", IconMail], ["lock", IconLock], ["camera", IconCamera], ["calendar-clock", IconClock],
  ["download", IconDownload], ["printer", IconPrinter], ["share", IconShare],
  ["whatsapp", IconBrandWhatsapp], ["copy", IconCopy], ["home", IconHome], ["wifi-off", IconWifiOff],
] as const;

const CUSTOM = [
  ["whistle", IconWhistle], ["yellow card", IconYellowCard], ["red card", IconRedCard],
  ["VAR screen", IconVarScreen],
] as const;

const MOTION = [
  { token: "--dur-tap", value: "120ms", feel: "Press feedback" },
  { token: "--dur-quick", value: "200ms", feel: "Hovers, toggles, small reveals" },
  { token: "--dur-move", value: "320ms", feel: "Sheets, toasts, step changes" },
  { token: "--dur-show", value: "560ms", feel: "Signature moments only" },
  { token: "--ease-kick", value: "cubic-bezier(.2,.8,.2,1)", feel: "Fast out, soft landing; the default" },
  { token: "--ease-bounce", value: "cubic-bezier(.34,1.56,.64,1)", feel: "A ball settling; badges and success" },
  { token: "--ease-glide", value: "cubic-bezier(.65,0,.35,1)", feel: "Page and layout changes" },
] as const;

const HAUSA = "Ɓ ɓ Ɗ ɗ Ƙ ƙ Ƴ ƴ — Ɗan wasan ƙwallon ƙafa";

export default async function StyleGuide() {
  if (!enabled()) notFound();
  const t = await getTranslations();

  const referee = [
    { icon: <IconWhistle />, label: t("referee.whistle"), box: "bg-surface text-text", text: "Your code is on its way." },
    { icon: <IconYellowCard />, label: t("referee.yellow"), box: "bg-warn-bg text-on-warn", text: "This phone number has 10 digits. Check it and try again." },
    { icon: <IconRedCard />, label: t("referee.red"), box: "bg-danger-bg text-danger", text: "Payment did not go through. You were not charged." },
    { icon: <IconVarScreen />, label: t("referee.var"), box: "bg-check-bg text-check", text: "Your photo is with your LGA coordinator. Usually under 24 hours." },
    { icon: <IconFlag />, label: t("referee.flag"), box: "bg-surface text-text", text: "This page is for coordinators. Sign in with a coordinator account." },
    { icon: <IconCheck />, label: t("referee.done"), box: "bg-pitch text-on-pitch", text: "Saved." },
  ];

  return (
    <div className="mx-auto max-w-wide px-4 py-8 sm:px-6">
      <header className="mb-12 motion-rise">
        <p className="font-mono text-xs text-muted">/styleguide · Phase 1</p>
        <h1 className="mt-2">{t("styleguide.title")}</h1>
        <p className="mt-3 max-w-measure text-md text-muted">{t("styleguide.lede")}</p>
        <p className="mt-4"><a href="/styleguide/components" className="font-bold">Components, in every state</a></p>
      </header>

      <Section id="brand" title="Logo">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-card border border-line bg-bg p-6">
            <Logo className="h-14 w-auto max-w-full text-text" />
            <p className="mt-4 text-xs text-muted">Horizontal lockup, inline. The dark parts follow the theme.</p>
          </div>
          <div className="rounded-card border border-line bg-[var(--night)] p-6 text-chalk turf-stripes">
            <Logo className="h-14 w-auto max-w-full" />
            <p className="mt-4 text-xs">On floodlit dark.</p>
          </div>
          <div className="flex items-center gap-6 rounded-card border border-line bg-bg p-6">
            <Logo variant="mark" className="h-16 w-auto text-text" />
            <Logo variant="mark" className="h-10 w-auto text-text" />
            <Logo variant="mark" className="h-6 w-auto text-text" />
          </div>
          <div className="rounded-card border border-line bg-surface p-6 text-xs text-muted">
            <p className="font-bold text-text">Files in /brand</p>
            <p className="mt-2">full, horizontal, mark and wordmark, each in colour, -on-dark, -white and -black.
              Traced from the raster logo; replace with the designer&rsquo;s source when it exists.</p>
            <p className="mt-2"><a href="/brand/kafriada-net-full.svg">kafriada-net-full.svg</a></p>
          </div>
        </div>
      </Section>

      <Section id="colour" title="Colour">
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {BRAND.map((c) => (
            <li key={c.token} className="flex gap-3 rounded-card border border-line bg-bg p-3">
              <span className={`size-14 shrink-0 rounded-input border border-line-strong ${c.swatch}`} />
              <span className="min-w-0 text-xs">
                <span className="block font-mono text-text">{c.token} · {c.hex}</span>
                <span className="block text-muted">{c.note}</span>
              </span>
            </li>
          ))}
        </ul>
        <h3 className="mt-8">Roles: these follow the theme</h3>
        <p className="mt-1 text-xs text-muted">Switch your device to dark mode to see floodlights.</p>
        <ul className="mt-3 flex flex-wrap gap-3">
          {ROLES.map((r) => (
            <li key={r.token} className="w-28 text-xs">
              <span className={`block h-12 rounded-input border border-line-strong ${r.swatch}`} />
              <span className="mt-1 block font-mono text-muted">{r.token}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section id="type" title="Type">
        <div className="rounded-card bg-surface p-6">
          <p className="font-display text-4xl font-extrabold uppercase italic leading-none">{t("styleguide.sampleHeadline")}</p>
          <p className="mt-4 max-w-measure text-md">{t("styleguide.sampleBody")}</p>
        </div>
        <dl className="mt-6 grid gap-4 md:grid-cols-3">
          <Font name="Display · Fira Sans Condensed 800" cls="font-display font-extrabold italic text-2xl uppercase" sample="Aisha Musa" hausa={HAUSA} />
          <Font name="Body · Andika 400 / 700" cls="font-body text-md" sample="Registration is free and takes two minutes." hausa={HAUSA} />
          <Font name="IDs and codes · Geist Mono" cls="font-mono text-lg scoreboard-digits" sample="KA-NG-JG-BKD-2026-000123" hausa="0 O · 1 l I · 5 S · 8 B" />
        </dl>
        <ul className="mt-6 space-y-2">
          {TYPE.map((s) => (
            <li key={s.token} className="flex flex-wrap items-baseline gap-x-4 border-b border-line pb-2">
              <span className="w-28 shrink-0 font-mono text-xs text-muted">{s.token}</span>
              <span className={`font-display font-extrabold ${s.cls}`}>Matchday</span>
              <span className="text-xs text-muted">{s.px}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section id="space" title="Space, shape, depth">
        <ul className="space-y-2">
          {SPACE.map((s) => (
            <li key={s.n} className="flex items-center gap-3 text-xs">
              <span className="w-10 font-mono text-muted">{s.n}</span>
              <span className={`h-3 rounded-sm bg-pitch ${s.cls}`} />
            </li>
          ))}
        </ul>
        <div className="mt-6 flex flex-wrap gap-4">
          <div className="grid size-28 place-items-center rounded-card bg-surface text-xs shadow-lift">card · 12 · lift</div>
          <div className="grid size-28 place-items-center rounded-card bg-surface text-xs shadow-float">sheet · float</div>
          <div className="grid h-12 place-items-center rounded-input border-2 border-line-strong px-4 text-xs">input · 4</div>
          <div className="grid h-14 place-items-center rounded-pill bg-pitch px-8 font-display text-md font-extrabold uppercase italic text-on-pitch">Pill · 56</div>
        </div>
        <p className="mt-3 text-xs text-muted">Touch targets at least 48 × 48. Primary buttons 56 tall on phones.</p>
      </Section>

      <Section id="icons" title="Icons">
        <p className="text-xs text-muted">Tabler, 2px stroke, server-rendered SVG. Always beside a word.</p>
        <ul className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-7">
          {ICONS.map(([name, Icon]) => (
            <li key={name} className="flex flex-col items-center gap-2 rounded-card border border-line p-3 text-center text-xs">
              <Icon size={24} stroke={2} aria-hidden="true" />
              <span className="text-muted">{name}</span>
            </li>
          ))}
        </ul>
        <h3 className="mt-8">Drawn for KAFRIADA NET</h3>
        <ul className="mt-3 flex flex-wrap gap-2">
          {CUSTOM.map(([name, Icon]) => (
            <li key={name} className="flex w-28 flex-col items-center gap-2 rounded-card border border-line p-3 text-xs">
              <Icon size={32} />
              <span className="text-muted">{name}</span>
            </li>
          ))}
          {(["GK", "DF", "MF", "FW"] as const).map((p) => (
            <li key={p} className="flex w-28 flex-col items-center gap-2 rounded-card border border-line p-3 text-xs">
              <IconPosition position={p} size={32} stroke={1.75} />
              <span className="text-muted">{t(`position.${p}`)}</span>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex items-end gap-4">
          {[16, 20, 24, 32].map((s) => (
            <span key={s} className="flex flex-col items-center gap-1 text-xs text-muted">
              <IconBallFootball size={s} aria-hidden="true" />{s}
            </span>
          ))}
        </div>
      </Section>

      <Section id="referee" title="The referee scale">
        <ul className="grid gap-3 md:grid-cols-2">
          {referee.map((r) => (
            <li key={r.label} className={`flex gap-3 rounded-card p-4 ${r.box}`}>
              <span className="shrink-0">{r.icon}</span>
              <span>
                <span className="block font-bold">{r.label}</span>
                <span className="block">{r.text}</span>
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-muted">
          Reference chip: <span className="rounded-pill bg-surface-2 px-3 py-1 font-mono text-text">REF 7K2·Q9X</span>
        </p>
      </Section>

      <Section id="pitch" title="Pitch lines">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-card bg-bg p-4 ring-1 ring-line">
            <Pitch draw className="w-full" />
            <p className="mt-2 text-xs text-muted">Full pitch, real proportions, chalked in with CSS.</p>
          </div>
          <div className="rounded-card border border-line bg-[var(--night)] p-4 turf-stripes [--chalk-line:var(--chalk)]">
            <Pitch className="w-full" />
            <p className="mt-2 text-xs text-chalk">Under floodlights, with mowing stripes. No image bytes.</p>
          </div>
          <div className="relative grid min-h-56 place-items-center overflow-hidden rounded-card bg-surface p-6">
            <CentreCircle draw className="absolute inset-0 m-auto h-full w-auto opacity-60" />
            <p className="relative font-display text-2xl font-extrabold uppercase italic">Centre circle</p>
          </div>
          <div className="flex flex-col items-center justify-end rounded-card bg-surface p-6">
            <PenaltyArc draw className="w-48" />
            <span className="-mt-1 grid h-14 place-items-center rounded-pill bg-pitch px-8 font-display text-md font-extrabold uppercase italic text-on-pitch">
              Register free
            </span>
            <p className="mt-3 text-xs text-muted">The penalty arc frames the one primary button.</p>
          </div>
        </div>
        <HalfwayLine className="my-8" />
        <div className="touchline pl-4 text-xs text-muted">Touchline: a page-edge rule for flows and timelines.</div>
      </Section>

      <Section id="scoreboard" title="Scoreboard">
        <div className="rounded-card bg-scoreboard p-5 text-scoreboard-text">
          <p className="text-xs uppercase tracking-widest opacity-80">KAFRIADA NET ID</p>
          <p className="mt-1 text-xl scoreboard-digits sm:text-2xl">KA-NG-JG-BKD-2026-000123</p>
          <p className="mt-4 flex items-baseline gap-3">
            <span className="font-display text-4xl font-extrabold text-scoreboard-accent scoreboard-digits">1,248</span>
            <span className="text-xs uppercase tracking-widest">registered so far</span>
          </p>
        </div>
      </Section>

      <Section id="motion" title="Motion">
        <table className="w-full text-left text-xs">
          <thead className="text-muted"><tr><th className="py-2 pr-4">Token</th><th className="py-2 pr-4">Value</th><th className="py-2">Feel</th></tr></thead>
          <tbody>
            {MOTION.map((m) => (
              <tr key={m.token} className="border-t border-line">
                <td className="py-2 pr-4 font-mono">{m.token}</td>
                <td className="py-2 pr-4 font-mono">{m.value}</td>
                <td className="py-2">{m.feel}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-6 flex flex-wrap items-center gap-6 text-xs">
          <span className="flex items-center gap-2"><IconBallFootball className="motion-bounce" aria-hidden="true" /> Waiting, 1–3 s</span>
          <span className="motion-flick inline-flex items-center gap-2 rounded-card bg-warn-bg p-3 text-on-warn"><IconYellowCard /> Card flicks in</span>
          <span className="motion-shake rounded-input border-2 border-danger px-3 py-2">Field error shakes once</span>
          <span className="motion-rise rounded-card bg-surface p-3">Rises like the logo&rsquo;s figure</span>
        </div>
        <p className="mt-3 text-xs text-muted">
          Only transform and opacity move. Reduced motion turns every movement into a fade. IDs, prices and error text never animate.
        </p>
      </Section>
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="mb-14">
      <h2 id={`${id}-h`} className="mb-4 font-extrabold uppercase italic">{title}</h2>
      {children}
    </section>
  );
}

function Font({ name, cls, sample, hausa }: { name: string; cls: string; sample: string; hausa: string }) {
  return (
    <div className="rounded-card border border-line p-4">
      <dt className="text-xs text-muted">{name}</dt>
      <dd className={`mt-2 ${cls}`}>{sample}</dd>
      <dd className={`mt-2 ${cls} text-md normal-case`}>{hausa}</dd>
    </div>
  );
}

import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";

import {
  IconArrowRight, IconBallFootball, IconCash, IconDownload, IconHome, IconIdBadge2, IconPhone,
  IconPrinter, IconQrcode, IconScan, IconSearch, IconShieldCheck, IconShirtSport, IconUser, IconUsersGroup,
} from "@/components/icons";
import {
  BigWhistle, EmptyBench, EmptyNet, HeldCard, KitRail, NoSignal, RaisedFlag, UnpluggedScoreboard,
} from "@/components/illustrations";
import { Button, IconButton } from "@/components/ui/Button";
import { DataTable } from "@/components/ui/DataTable";
import { Checkbox, CodeInput, ErrorSummary, Field, Fieldset, Input, PhoneInput, Select } from "@/components/ui/Field";
import { TabBar } from "@/components/ui/Navigation";
import { Notice } from "@/components/ui/Notice";
import { Sheet, Toast } from "@/components/ui/Overlay";
import { EmptyState, PageState, Skeleton } from "@/components/ui/PageState";
import { Pill, VerifiedBadge } from "@/components/ui/Pill";
import { PlayerCard, PrintCard, type PlayerCardData } from "@/components/ui/PlayerCard";
import { PositionPicker } from "@/components/ui/PositionPicker";
import { RefChip } from "@/components/ui/RefChip";
import { KuidStrip, Scoreboard } from "@/components/ui/Scoreboard";
import { Spinner } from "@/components/ui/Spinner";
import { Stepper } from "@/components/ui/Stepper";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { styleguideEnabled } from "@/lib/styleguide";

export const metadata: Metadata = { title: "Components", robots: { index: false } };
export const dynamic = "force-dynamic";

const SAMPLE: PlayerCardData = {
  kuid: "KA-NG-JG-BKD-2026-000123",
  fullName: "Aisha Musa",
  position: "Central midfielder",
  lgaName: "Birnin Kudu",
  stateName: "Jigawa",
  year: 2026,
  verified: true,
};
const UNVERIFIED: PlayerCardData = { ...SAMPLE, kuid: "KA-NG-JG-DUT-2026-004781", fullName: "Ɗanjuma Ƙasimu", position: "Goalkeeper", lgaName: "Dutse", verified: false };

export default async function Components() {
  if (!styleguideEnabled()) notFound();
  const t = await getTranslations();
  const labels = { idLabel: t("ui.idLabel"), verified: t("ui.verified"), photoAlt: t("ui.photoAlt", { name: SAMPLE.fullName }), noPhoto: t("ui.noPhoto") };
  const positions = t.raw("footballPositions") as Record<string, string>;
  const ic = (I: typeof IconHome) => <I size={22} aria-hidden="true" />;

  return (
    <div className="mx-auto max-w-wide px-4 py-8 sm:px-6">
      <header className="mb-12">
        <p className="font-mono text-xs text-muted"><a href="/styleguide">/styleguide</a> / components · Phase 2</p>
        <h1 className="mt-2">Components</h1>
        <p className="mt-3 max-w-measure text-md text-muted">
          Every building block in each of its states. Everything here works with JavaScript off; the few
          enhancements (copy, the pending button) are marked.
        </p>
      </header>

      <Block id="buttons" title="Button">
        <Row>
          <Button variant="primary" size="lg" iconAfter={<IconArrowRight size={20} aria-hidden="true" />}>Register free</Button>
          <Button variant="primary">Save</Button>
          <Button variant="secondary" icon={<IconDownload size={20} aria-hidden="true" />}>Download card</Button>
          <Button variant="ghost">Look up an ID</Button>
          <Button variant="danger">Withdraw</Button>
          <Button variant="primary" disabled>Disabled</Button>
          <Button href="/find" variant="secondary" icon={<IconSearch size={20} aria-hidden="true" />}>As a link</Button>
        </Row>
        <Row>
          <IconButton label="Print" icon={<IconPrinter aria-hidden="true" />} />
          <IconButton label="Scan a card" icon={<IconScan aria-hidden="true" />} />
          <form action="/styleguide/components#buttons" className="w-full max-w-xs">
            <SubmitButton pendingLabel="Creating your ID…" icon={<IconIdBadge2 size={20} aria-hidden="true" />}>
              Create my ID
            </SubmitButton>
          </form>
        </Row>
        <Note>SubmitButton: with JavaScript it locks and shows &ldquo;Creating your ID…&rdquo; with the ball bouncing.</Note>
      </Block>

      <Block id="spinner" title="Spinner">
        <Row>
          <Spinner size={96} label={t("ui.loading")} />
          <Spinner size={64} />
          <Spinner size={44} />
          <Spinner size={26} />
          <span className="rounded-card bg-[var(--night)] p-4 [--line-strong:var(--chalk)]"><Spinner size={64} className="text-chalk" /></span>
        </Row>
        <Note>The logo&rsquo;s figure rising on each beat inside a chalk centre circle. CSS only. Under reduced motion it stops turning and only fades.</Note>
      </Block>

      <Block id="fields" title="Fields">
        <div className="grid gap-8 md:grid-cols-2">
          <Fieldset legend="You">
            <Field name="sg_name" label="Full name" hint="As your family and coach know you." icon={<IconUser size={18} />}>
              {(a) => <Input {...a} defaultValue="Aisha Musa" autoComplete="name" />}
            </Field>
            <Field name="sg_phone" label="Phone number" icon={<IconPhone size={18} />}>
              {(a) => <PhoneInput {...a} defaultValue="0803 000 0000" />}
            </Field>
            <Field name="sg_lga" label="Local government area">
              {(a) => (
                <Select {...a} defaultValue="bkd">
                  <option value="">Choose an area</option>
                  <option value="bkd">Birnin Kudu</option>
                  <option value="dut">Dutse</option>
                </Select>
              )}
            </Field>
            <Field name="sg_email" label="Email" optional optionalLabel={t("ui.optional")}>
              {(a) => <Input {...a} type="email" />}
            </Field>
          </Fieldset>
          <Fieldset legend="With errors">
            <ErrorSummary
              title={t("ui.formErrors")}
              errors={[
                { field: "sg_phone_bad", message: "This phone number has 10 digits. Check it and try again." },
                { field: "sg_consent", message: "Tick the box to agree to the privacy notice." },
              ]}
            />
            <Field name="sg_phone_bad" label="Phone number" error="This phone number has 10 digits. Check it and try again.">
              {(a) => <PhoneInput {...a} defaultValue="0803 000 000" />}
            </Field>
            <Field name="sg_code" label="Code from your message" hint="Six digits.">
              {(a) => <CodeInput {...a} defaultValue="482913" />}
            </Field>
            <Checkbox name="sg_consent" error="Tick the box to agree to the privacy notice.">
              I have read the <a href="/privacy">privacy notice</a> and agree to it.
            </Checkbox>
          </Fieldset>
        </div>
      </Block>

      <Block id="position" title="Position picker">
        <div className="max-w-sm">
          <PositionPicker legend="Your main position" value="Central midfielder" labels={positions} />
        </div>
        <Note>Ordinary radio buttons on a pitch: keyboard, screen reader and JavaScript-off all work.</Note>
      </Block>

      <Block id="stepper" title="Stepper">
        <div className="max-w-measure space-y-8">
          <Stepper steps={["You", "Your game", "Your account"]} current={0} label={t("ui.progress")} progressText={t("ui.stepOf", { current: 1, total: 3 })} />
          <Stepper steps={["Photo", "Pay", "Review"]} current={2} label={t("ui.progress")} progressText={t("ui.stepOf", { current: 3, total: 3 })} />
        </div>
      </Block>

      <Block id="card" title="Player card">
        <div className="flex flex-wrap items-start gap-6">
          <PlayerCard data={SAMPLE} labels={labels} size="lg" />
          <PlayerCard data={UNVERIFIED} labels={{ ...labels, photoAlt: t("ui.photoAlt", { name: UNVERIFIED.fullName }) }} />
          <div className="w-full max-w-sm space-y-2">
            <PlayerCard data={SAMPLE} labels={labels} size="sm" as="div" />
            <PlayerCard data={UNVERIFIED} labels={labels} size="sm" as="div" />
          </div>
        </div>
        <h3 className="mt-10">Printed, 85.6 × 54 mm</h3>
        <div className="mt-3 overflow-x-auto">
          <PrintCard
            data={SAMPLE}
            labels={labels}
            qrSrc={`data:image/svg+xml,${encodeURIComponent(QR_PLACEHOLDER)}`}
            back={{ scan: t("card.scan"), scanHelp: t("card.scanHelp"), issuedBy: t("card.issuedBy") }}
          />
        </div>
        <Note>Printed on the plate tokens: the same in light and dark. The backend PNG/PDF renderer must match this in Phase 4.</Note>
      </Block>

      <Block id="scoreboard" title="KUID strip and scoreboard">
        <div className="grid gap-4 md:grid-cols-2">
          <KuidStrip kuid={SAMPLE.kuid} label={t("ui.idLabel")} />
          <div className="w-64"><KuidStrip kuid={SAMPLE.kuid} label="At 256px" /></div>
        </div>
        <Scoreboard
          className="mt-4"
          items={[
            { label: "In the queue", value: "17" },
            { label: "Cash today", value: "₦12,500", accent: true },
            { label: "Approved", value: "42" },
          ]}
        />
      </Block>

      <Block id="pills" title="Pill and badge">
        <Row>
          <VerifiedBadge verified labels={{ verified: t("ui.verified"), unverified: t("ui.unverified") }} />
          <VerifiedBadge verified={false} labels={{ verified: t("ui.verified"), unverified: t("ui.unverified") }} />
          <Pill tone="check" icon={<IconShieldCheck size={16} aria-hidden="true" />}>Being checked</Pill>
          <Pill tone="warn">Payment pending</Pill>
          <Pill tone="bad">Not completed</Pill>
          <Pill tone="good" icon={<IconCash size={16} aria-hidden="true" />}>Paid</Pill>
        </Row>
      </Block>

      <Block id="notices" title="Notices: the referee scale">
        <div className="grid gap-3 md:grid-cols-2">
          <Notice signal="whistle" title="Your code is on its way.">
            <p>Your ID is already yours. The code only confirms your number.</p>
          </Notice>
          <Notice signal="yellow" title="Too many attempts." action={<Button variant="secondary">Send a new code</Button>}>
            <p>Wait 10 minutes, then ask for a new code. Your ID is safe.</p>
          </Notice>
          <Notice signal="red" title="Payment did not go through." reference="7K2Q9X" referenceHelp={t("ui.tellCoordinator")}>
            <p>You were not charged. Try again, or pay your LGA coordinator in cash.</p>
          </Notice>
          <Notice signal="var" title="Your photo is with your LGA coordinator.">
            <p>Usually under 24 hours. We will send you a message.</p>
          </Notice>
          <Notice signal="flag" title="This page is for coordinators.">
            <p>Sign in with a coordinator account.</p>
          </Notice>
          <Notice signal="done" title="Saved." />
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-4">
          <RefChip code="7K2Q9X" help={t("ui.tellCoordinator")} copyLabel={t("ui.copy")} copiedLabel={t("ui.copied")} />
          <Toast>{t("ui.copied")}</Toast>
        </div>
        <Note>The copy button appears only with JavaScript. A toast is never the only sign that something happened.</Note>
      </Block>

      <Block id="states" title="Page states">
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel>
            <PageState art={<EmptyNet />} title="No athlete with that ID" reference="NF1A2B"
              action={<Button href="/find" block size="lg">Look up an ID</Button>} secondary={<a href="/">Back to home</a>}>
              Check the ID printed on the card and try again.
            </PageState>
          </Panel>
          <Panel>
            <PageState art={<RaisedFlag />} title="This page is for coordinators"
              action={<Button href="/sign-in" block size="lg">Sign in</Button>}>
              Sign in with a coordinator account.
            </PageState>
          </Panel>
          <Panel>
            <PageState art={<BigWhistle />} title="You were signed out"
              action={<Button href="/sign-in" block size="lg">Sign in again</Button>}>
              You were signed out to keep your account safe.
            </PageState>
          </Panel>
          <Panel>
            <PageState art={<HeldCard colour="yellow" />} title="Too many attempts"
              action={<Button variant="secondary" block size="lg">Try again in 10 minutes</Button>}>
              Wait a little, then try again. Nothing was lost.
            </PageState>
          </Panel>
          <Panel>
            <PageState art={<HeldCard colour="red" />} title={t("errors.serverTitle")} reference="7K2Q9X" referenceHelp={t("errors.refHelp")}
              action={<Button block size="lg">{t("errors.retry")}</Button>} secondary={<a href="/">{t("errors.home")}</a>}>
              {t("errors.serverText")}
            </PageState>
          </Panel>
          <Panel>
            <PageState art={<EmptyNet />} title={t("errors.notFoundTitle")}
              action={<Button href="/" block size="lg">{t("errors.home")}</Button>}>
              {t("errors.notFoundText")}
            </PageState>
          </Panel>
          <Panel>
            <PageState art={<HeldCard colour="red" />} title={t("errors.unreachableTitle")}
              action={<Button block size="lg">{t("errors.retry")}</Button>}>
              {t("errors.unreachableText")}
            </PageState>
          </Panel>
          <Panel>
            <PageState art={<NoSignal />} title={t("errors.offlineTitle")}
              action={<Button block size="lg">{t("errors.retry")}</Button>}>
              {t("errors.offlineText")}
            </PageState>
          </Panel>
        </div>
      </Block>

      <Block id="empty" title="Empty states and loading">
        <div className="grid gap-4 md:grid-cols-2">
          <EmptyState art={<EmptyBench />} title="No players yet" action={<Button icon={<IconUsersGroup size={20} aria-hidden="true" />}>Invite a player</Button>}>
            Invite players by their KAFRIADA NET ID.
          </EmptyState>
          <EmptyState art={<KitRail />} title="No clubs yet" action={<Button variant="secondary">Find a club</Button>}>
            When a club adds you, it appears here.
          </EmptyState>
          <EmptyState art={<UnpluggedScoreboard />} title="No payments yet">
            Payments you make appear here.
          </EmptyState>
          <div className="rounded-card border border-line p-4">
            <Skeleton label={t("ui.loading")} />
            <p className="mt-4 flex items-center gap-2 text-xs text-muted">
              <IconBallFootball size={20} className="motion-bounce" aria-hidden="true" /> 1 to 3 seconds: the ball. Longer: the shape of what is coming.
            </p>
          </div>
        </div>
      </Block>

      <Block id="nav" title="Sheet, tab bar, table">
        <Row>
          <Sheet trigger={<><IconQrcode aria-hidden="true" /> Open a sheet</>} title="Share your card" closeLabel={t("nav.close")}>
            <p className="text-muted">A sheet built on details: it opens and closes with JavaScript off.</p>
            <Button block size="lg" className="mt-4">Share on WhatsApp</Button>
          </Sheet>
        </Row>
        <div className="mt-4 rounded-card border border-line p-4">
          <p className="mb-2 text-xs text-muted">Athlete tabs. On a phone they sit at the bottom of the screen; here, on wide screens, as a rail.</p>
          <div className="[&_nav]:static [&_nav]:border-0 [&>div]:hidden">
            <TabBar
              label="Athlete"
              current="/card"
              items={[
                { href: "/me", label: t("tabs.home"), icon: ic(IconHome) },
                { href: "/card", label: t("tabs.card"), icon: ic(IconIdBadge2) },
                { href: "/clubs", label: t("tabs.clubs"), icon: ic(IconShirtSport) },
                { href: "/verify", label: t("tabs.verify"), icon: ic(IconShieldCheck) },
                { href: "/details", label: t("tabs.me"), icon: ic(IconUser) },
              ]}
            />
          </div>
        </div>
        <DataTable
          className="mt-6"
          caption="Squad"
          columns={[
            { key: "name", label: "Player" },
            { key: "kuid", label: "KAFRIADA NET ID", mono: true },
            { key: "status", label: "Status" },
            { key: "since", label: "Joined", align: "end" },
          ]}
          rows={[
            { id: "1", name: "Aisha Musa", kuid: SAMPLE.kuid, status: <VerifiedBadge verified labels={{ verified: t("ui.verified"), unverified: t("ui.unverified") }} />, since: "Mar 2026" },
            { id: "2", name: "Ɗanjuma Ƙasimu", kuid: UNVERIFIED.kuid, status: <VerifiedBadge verified={false} labels={{ verified: t("ui.verified"), unverified: t("ui.unverified") }} />, since: "Apr 2026" },
          ]}
        />
      </Block>
    </div>
  );
}

function Block({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="mb-16 scroll-mt-20">
      <h2 id={`${id}-h`} className="mb-5 uppercase">{title}</h2>
      {children}
    </section>
  );
}
function Row({ children }: { children: React.ReactNode }) {
  return <div className="mb-4 flex flex-wrap items-center gap-3">{children}</div>;
}
function Note({ children }: { children: React.ReactNode }) {
  return <p className="mt-3 text-xs text-muted">{children}</p>;
}
function Panel({ children }: { children: React.ReactNode }) {
  return <div className="rounded-card border border-line">{children}</div>;
}

/** A stand-in square for the styleguide only; real cards use /qr/{kuid}. */
const QR_PLACEHOLDER = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 21 21" shape-rendering="crispEdges"><rect width="21" height="21" fill="#fff"/><path fill="#0A0F0B" d="M0 0h7v7H0zM14 0h7v7h-7zM0 14h7v7H0zM2 2h3v3H2zM16 2h3v3h-3zM2 16h3v3H2zM9 1h2v2H9zM9 5h3v2H9zM8 9h5v1H8zM10 11h4v2h-4zM15 9h4v2h-4zM9 15h2v4H9zM13 15h4v2h-4zM16 18h4v2h-4z"/><path fill="#fff" d="M1 1h5v5H1zM15 1h5v5h-5zM1 15h5v5H1z"/><path fill="#0A0F0B" d="M2 2h3v3H2zM16 2h3v3h-3zM2 16h3v3H2z"/></svg>`;

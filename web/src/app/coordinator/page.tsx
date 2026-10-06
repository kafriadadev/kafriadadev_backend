import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconChevronRight, IconCreditCard, IconPrinter, IconSearch, IconVarScreen } from "@/components/icons";
import { RaisedFlag } from "@/components/illustrations";
import { Button } from "@/components/ui/Button";
import { CoordinatorShell } from "@/components/ui/CoordinatorShell";
import { Field, Select } from "@/components/ui/Field";
import { Notice, type Signal } from "@/components/ui/Notice";
import { Page, PageHead } from "@/components/ui/Page";
import { PageState } from "@/components/ui/PageState";
import { Scoreboard } from "@/components/ui/Scoreboard";
import { ApiError, getCoordinatorDashboard, getMe, listLgas, type CoordinatorDashboard, type Me } from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("coord"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

/** Over this many hours a waiting case is amber; over the target, red. */
const AMBER_HOURS = 18;
const TARGET_HOURS = 24;

/**
 * The coordinator's home (CRD-01): what needs doing today in one LGA, on a
 * phone, in a hall. An LGA coordinator's LGA comes from their role; a state
 * coordinator or an administrator picks one. Every number is the API's, and
 * everything is a link.
 */
export default async function CoordinatorPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("coord");
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let me: Me;
  try {
    me = await getMe(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }
  const own = me.roles.find((r) => r.scope_kind === "lga")?.scope_id ?? "";
  const canChoose = me.roles.some((r) => r.scope_kind === "state" || r.scope_kind === "global");
  const lga = one(params.lga) || own;

  if (!lga) {
    return canChoose ? (
      <Page><PageHead title={t("title")} /><Chooser /></Page>
    ) : (
      <PageState art={<RaisedFlag />} title={t("noLga")} action={<Button href="/me" size="lg" block>{(await getTranslations("club"))("back")}</Button>}>
        {t("noLgaText")}
      </PageState>
    );
  }

  let d: CoordinatorDashboard;
  try {
    d = await getCoordinatorDashboard(token, lga);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403 || error.status === 404) {
        return (
          <Page>
            <PageState art={<RaisedFlag />} title={t("noAccess")}>{t("noAccessText")}</PageState>
            {canChoose ? <Chooser /> : null}
          </Page>
        );
      }
    }
    throw error;
  }

  const q = `lga=${encodeURIComponent(d.lga_id)}`;
  const hours = d.oldest_waiting_hours;
  const signal: Signal = hours !== null && hours >= TARGET_HOURS ? "red" : hours !== null && hours >= AMBER_HOURS ? "yellow" : "var";
  const jobs = [
    { href: `/review?${q}`, icon: <IconVarScreen size={28} aria-hidden="true" />, title: t("review"), text: t("reviewText"), badge: d.to_review || null },
    { href: `/coordinator/find?${q}`, icon: <IconSearch size={28} aria-hidden="true" />, title: t("find"), text: t("findText") },
    ...(d.can_assist && !d.cap_reached ? [{ href: `/assist-pay?${q}`, icon: <IconCreditCard size={28} aria-hidden="true" />, title: t("pay"), text: t("payText") }] : []),
    { href: `/coordinator/cards?${q}`, icon: <IconPrinter size={28} aria-hidden="true" />, title: t("cards"), text: t("cardsText") },
  ];

  return (
    <CoordinatorShell current="today" lga={d.lga_id} token={token}>
      <PageHead eyebrow={t("eyebrow", { lga: d.lga_name, name: me.full_name })} title={t("title")} />

      <Scoreboard
        items={[
          { label: t("stats.registered"), value: d.registered },
          { label: t("stats.paid"), value: d.paid },
          { label: t("stats.review"), value: d.to_review, accent: d.to_review > 0 },
          { label: t("stats.clubs"), value: d.clubs },
        ]}
      />

      <div className="mt-4">
        {d.to_review === 0 ? (
          <Notice signal="done" title={t("clear")}><p>{t("clearText")}</p></Notice>
        ) : (
          <Notice signal={signal} title={t("oldest", { age: hours === null || hours < 1 ? t("underHour") : `${hours}h` })}
            action={<Button href={`/review?${q}`} size="lg">{t("reviewNow")}</Button>}>
            <p>{t("waitingText", { count: d.to_review })}</p>
          </Notice>
        )}
      </div>

      <section aria-labelledby="todo" className="mt-8">
        <h2 id="todo" className="text-lg uppercase">{t("todo")}</h2>
        <ul className="mt-3 grid gap-3 sm:grid-cols-2">
          {jobs.map((j) => (
            <li key={j.href}>
              <a href={j.href} className="flex min-h-24 items-center gap-4 rounded-card border-2 border-line-strong p-4 text-text no-underline hover:border-pitch hover:bg-surface">
                <span className="grid size-14 shrink-0 place-items-center rounded-full bg-pitch text-on-pitch">{j.icon}</span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 font-display text-xl font-extrabold uppercase italic">
                    {j.title}
                    {"badge" in j && j.badge ? <span className="rounded-pill bg-warn-bg px-2 font-body text-xs not-italic text-on-warn">{j.badge}</span> : null}
                  </span>
                  <span className="block text-xs text-muted">{j.text}</span>
                </span>
                <IconChevronRight className="shrink-0 text-muted" aria-hidden="true" />
              </a>
            </li>
          ))}
        </ul>
      </section>

      {d.can_assist ? (
        <section aria-labelledby="cash" className="mt-8 rounded-card bg-surface p-4">
          <h2 id="cash" className="text-lg uppercase">{t("cash")}</h2>
          <p className="mt-2 flex items-baseline gap-3">
            <span className="whitespace-nowrap font-display text-3xl font-extrabold italic scoreboard-digits">{formatNaira(d.collected_kobo)}</span>
            <span className="text-muted">{t("payments", { count: d.collected_count })}</span>
          </p>
          <p className="mt-1 text-xs text-muted">{t("limit", { amount: formatNaira(d.limit_kobo), count: d.limit_count })}</p>
          {d.cap_reached ? <Notice signal="yellow" title={t("capped")} className="mt-3" /> : null}
        </section>
      ) : null}

      {canChoose ? <div className="mt-8"><Chooser current={d.lga_id} /></div> : null}
    </CoordinatorShell>
  );
}

async function Chooser({ current }: { current?: string }) {
  const t = await getTranslations("coord");
  let options: Awaited<ReturnType<typeof listLgas>> = [];
  try {
    options = await listLgas();
  } catch {
    // An unreachable list leaves an empty selector; the page still works for the LGA already chosen.
  }
  return (
    <form method="get" className="flex flex-wrap items-end gap-3">
      <Field name="lga" label={t("choose")} className="min-w-48 flex-1">
        {(a) => (
          <Select {...a} defaultValue={current ?? ""}>
            <option value="">{t("chooseOne")}</option>
            {options.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </Select>
        )}
      </Field>
      <Button type="submit" variant="secondary">{t("show")}</Button>
    </form>
  );
}

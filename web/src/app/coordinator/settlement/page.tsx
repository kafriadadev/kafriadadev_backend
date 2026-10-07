import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconDownload, IconSearch } from "@/components/icons";
import { EmptyNet, RaisedFlag } from "@/components/illustrations";
import { Button } from "@/components/ui/Button";
import { CoordinatorShell } from "@/components/ui/CoordinatorShell";
import { DataTable } from "@/components/ui/DataTable";
import { Field, Input, Select } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { PageHead } from "@/components/ui/Page";
import { EmptyState, PageState } from "@/components/ui/PageState";
import { Pill, type Tone } from "@/components/ui/Pill";
import { Scoreboard } from "@/components/ui/Scoreboard";
import { ApiError, getMe, getSettlement, type Settlement, type SettlementLine } from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("settle"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

const TONE: Record<SettlementLine["status"], Tone> = {
  success: "good",
  pending: "warn",
  frozen: "bad",
  abandoned: "bad",
  failed: "neutral",
};

const lagosTime = (iso: string): string =>
  new Intl.DateTimeFormat("en-NG", {
    timeZone: "Africa/Lagos", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(new Date(iso));

/**
 * Cash settlement (CRD-05). Every assisted payment is cash in a coordinator's
 * hand; only a confirmed one is in the ledger. The gap between the two totals
 * is what has to be chased or handed in, so it leads the screen. A plain GET
 * form picks the dates; the CSV is the same lines for a spreadsheet.
 */
export default async function SettlementPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("settle");
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  let own = "";
  try {
    own = (await getMe(token)).roles.find((r) => r.scope_kind === "lga")?.scope_id ?? "";
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }
  const lga = one(params.lga) || own;
  const since = one(params.since);
  const until = one(params.until);
  const mine = one(params.mine) !== "false";
  if (!lga) {
    return (
      <PageState art={<RaisedFlag />} title={t("noLga")} action={<Button href="/coordinator" size="lg" block>{t("dashboard")}</Button>}>
        {t("noLgaText")}
      </PageState>
    );
  }

  let report: Settlement | null = null;
  let problem = "";
  try {
    report = await getSettlement(token, lga, { since, until, mine });
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 401) redirect("/sign-in?ended=1");
    if (error.status === 403) problem = t("forbidden");
    else if (error.status === 422) problem = t("badDates");
    else throw error;
  }
  const query = report
    ? new URLSearchParams({ lga, since: report.since, until: report.until, mine: String(mine) })
    : null;

  return (
    <CoordinatorShell current="settlement" lga={lga} token={token}>
      <PageHead eyebrow={t("eyebrow")} title={t("title")} lede={t("lede")} />
      {problem ? <Notice signal="red" title={t("error")} className="mb-6"><p>{problem}</p></Notice> : null}

      <form method="get" className="grid gap-4 sm:grid-cols-2 sm:items-end xl:grid-cols-[1fr_1fr_1fr_auto]">
        <input type="hidden" name="lga" value={lga} />
        <Field name="since" label={t("from")}>{(a) => <Input {...a} type="date" defaultValue={report?.since ?? since} />}</Field>
        <Field name="until" label={t("to")}>{(a) => <Input {...a} type="date" defaultValue={report?.until ?? until} />}</Field>
        <Field name="mine" label={t("whose")}>
          {(a) => (
            <Select {...a} defaultValue={String(mine)}>
              <option value="true">{t("mine")}</option>
              <option value="false">{t("everyone")}</option>
            </Select>
          )}
        </Field>
        <Button type="submit" variant="secondary" icon={<IconSearch size={20} aria-hidden="true" />}>{t("show")}</Button>
      </form>

      {report && !report.lines.length ? (
        <EmptyState art={<EmptyNet />} title={t("none")} className="mt-8">{t("noneText")}</EmptyState>
      ) : null}

      {report && report.lines.length ? (
        <section aria-labelledby="totals" className="mt-8 space-y-4">
          <h2 id="totals" className="sr-only">{t("title")}</h2>
          <Scoreboard
            items={[
              { label: t("collected"), value: formatNaira(report.collected_kobo) },
              { label: t("confirmed"), value: formatNaira(report.confirmed_kobo) },
              { label: t("difference"), value: formatNaira(report.difference_kobo), accent: report.difference_kobo !== 0 },
            ]}
          />
          {report.difference_kobo === 0 ? (
            <Notice signal="done" title={t("balanced")}><p>{t("balancedText")}</p></Notice>
          ) : (
            <Notice signal={report.abandoned_count || report.review_count ? "red" : "yellow"} title={t("short", { amount: formatNaira(report.difference_kobo) })}>
              <p>{t("shortText", { pending: report.pending_count, review: report.review_count, abandoned: report.abandoned_count }).trim()}</p>
            </Notice>
          )}
          {report.truncated ? <Notice signal="whistle" title={t("truncated")} /> : null}
          {query ? (
            <Button href={`/coordinator/settlement/csv?${query}`} variant="secondary" icon={<IconDownload size={20} aria-hidden="true" />}>{t("csv")}</Button>
          ) : null}
          <DataTable
            caption={t("caption", { since: report.since, until: report.until })}
            columns={[
              { key: "date", label: t("date") },
              { key: "athlete", label: t("athlete") },
              ...(mine ? [] : [{ key: "by", label: t("by") }]),
              { key: "amount", label: t("amount"), align: "end" as const, mono: true },
              { key: "status", label: t("status") },
            ]}
            rows={report.lines.map((x) => ({
              id: x.reference,
              date: <span className="whitespace-nowrap">{lagosTime(x.created_at)}</span>,
              athlete: (
                <span>
                  <strong>{x.athlete_name}</strong>
                  <span className="block whitespace-nowrap font-mono text-xs text-muted">{x.kuid}</span>
                </span>
              ),
              by: x.coordinator_name,
              amount: formatNaira(x.amount_kobo),
              status: <Pill tone={TONE[x.status]}>{t(`status_${x.status}`)}</Pill>,
            }))}
          />
        </section>
      ) : null}
    </CoordinatorShell>
  );
}

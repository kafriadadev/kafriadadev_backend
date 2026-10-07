import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconDownload, IconPrinter, IconSearch } from "@/components/icons";
import { RaisedFlag } from "@/components/illustrations";
import { Button } from "@/components/ui/Button";
import { Iso } from "@/components/iso/Iso";
import { cardPrinter } from "@/components/iso/scenes";
import { CoordinatorShell } from "@/components/ui/CoordinatorShell";
import { Field, Input, Select } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { PageHead } from "@/components/ui/Page";
import { EmptyState, PageState } from "@/components/ui/PageState";
import { Pager } from "@/components/ui/Pager";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ApiError, getCardBatch, getMe, type CardBatch } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { markPrintedAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("cards2"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

/**
 * Bulk QR card printing (CRD-06): a registration drive into a stack of cards.
 * A plain GET form filters by date and print status. Printing is the
 * browser's own: on paper only the cards appear, eight to an A4 sheet at real
 * card size (85.6 × 54 mm). The PDF is the same sheets for a browser that
 * cannot print. A large batch is paged, never one enormous document.
 */
export default async function CardsPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("cards2");
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
  const unprinted = one(params.unprinted) !== "false";
  const page = Math.max(Number.parseInt(one(params.page) || "1", 10) || 1, 1);
  if (!lga) {
    return (
      <PageState art={<RaisedFlag />} title={t("noLga")} action={<Button href="/coordinator" size="lg" block>{t("dashboard")}</Button>}>
        {t("noLgaText")}
      </PageState>
    );
  }

  let batch: CardBatch | null = null;
  let problem = one(params.error);
  try {
    batch = await getCardBatch(token, lga, { since, until, unprinted, page });
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    if (error.status === 401) redirect("/sign-in?ended=1");
    if (error.status === 403) problem = t("forbidden");
    else if (error.status === 422) problem = t("badDates");
    else throw error;
  }
  const keep = (extra: Record<string, string> = {}) =>
    new URLSearchParams({ lga, since, until, unprinted: String(unprinted), page: String(page), ...extra });
  const onPage = batch?.people.length ?? 0;
  const sheets = batch ? Math.ceil(onPage / batch.per_sheet) : 0;
  const marked = one(params.marked);

  return (
    <CoordinatorShell current="cards" lga={lga} token={token}>
      <div className="print:hidden">
        <PageHead eyebrow={t("eyebrow")} title={t("title")} lede={t("lede")} />
        <div className="mb-6 space-y-3 empty:hidden">
          {problem ? <Notice signal="red" title={t("error")}><p>{problem}</p></Notice> : null}
          {marked ? <Notice signal="done" title={t("recorded")}><p>{t("marked", { count: Number(marked) })}</p></Notice> : null}
        </div>

        <form method="get" className="grid gap-4 sm:grid-cols-2 sm:items-end xl:grid-cols-[1fr_1fr_1fr_auto]">
          <input type="hidden" name="lga" value={lga} />
          <Field name="since" label={t("from")}>{(a) => <Input {...a} type="date" defaultValue={since} />}</Field>
          <Field name="until" label={t("to")}>{(a) => <Input {...a} type="date" defaultValue={until} />}</Field>
          <Field name="unprinted" label={t("show")}>
            {(a) => (
              <Select {...a} defaultValue={String(unprinted)}>
                <option value="true">{t("unprinted")}</option>
                <option value="false">{t("all")}</option>
              </Select>
            )}
          </Field>
          <Button type="submit" variant="secondary" icon={<IconSearch size={20} aria-hidden="true" />}>{t("find")}</Button>
        </form>

        {batch && batch.total === 0 ? (
          <EmptyState wideArt art={<Iso fig={cardPrinter(0)} name="printer" />} title={t("none")} className="mt-8">{t("noneText")}</EmptyState>
        ) : null}
        {batch && batch.total > 0 ? (
          <section aria-labelledby="batch" className="mt-8 space-y-4">
            <h2 id="batch" className="text-lg uppercase">
              {t("summary", { total: batch.total, sheets: Math.ceil(batch.total / batch.per_sheet), per: batch.per_sheet })}
            </h2>
            {batch.pages > 1 ? <p className="text-muted">{t("pageOf", { page: batch.page, pages: batch.pages, cards: onPage, sheets })}</p> : null}
            <div className="grid items-center gap-4 rounded-card bg-surface p-4 sm:grid-cols-[12rem_1fr]">
              <Iso fig={cardPrinter(Math.min(onPage, batch.per_sheet))} name="printer" className="mx-auto max-w-[12rem]" />
              <p className="flex gap-2 text-muted"><IconPrinter className="shrink-0" aria-hidden="true" />{t("howTo")}</p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button href={`/coordinator/cards/pdf?${keep()}`} icon={<IconDownload size={20} aria-hidden="true" />}>{t("pdf")}</Button>
              <form action={markPrintedAction}>
                <input type="hidden" name="lga" value={lga} />
                <input type="hidden" name="since" value={since} />
                <input type="hidden" name="until" value={until} />
                <input type="hidden" name="unprinted" value={String(unprinted)} />
                <input type="hidden" name="page" value={String(page)} />
                <input type="hidden" name="kuids" value={batch.people.map((p) => p.kuid).join(",")} />
                <SubmitButton variant="secondary" size="md" block={false} pendingLabel={t("marking")}>{t("mark")}</SubmitButton>
              </form>
            </div>
            <Pager label={t("page", { n: batch.page })}
              prev={batch.page > 1 ? `/coordinator/cards?${keep({ page: String(batch.page - 1) })}` : null}
              next={batch.page < batch.pages ? `/coordinator/cards?${keep({ page: String(batch.page + 1) })}` : null}
              labels={{ prev: t("prev"), next: t("next") }} />
          </section>
        ) : null}
      </div>

      {batch && batch.total > 0 ? (
        // On screen, a preview grid. On paper, two columns of real-size cards,
        // eight to a sheet, a page break after every eighth.
        <div aria-label={t("title")} className="mt-8 grid gap-3 sm:grid-cols-2 print:mt-0 print:grid-cols-[85.6mm_85.6mm] print:justify-center print:gap-x-[6mm] print:gap-y-[5mm]">
          {batch.people.map((p, i) => (
            <figure key={p.kuid} className={`m-0 break-inside-avoid ${(i + 1) % 8 === 0 ? "print:break-after-page" : ""}`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`/card/${encodeURIComponent(p.kuid)}/card.png`} alt={t("alt", { name: p.full_name, kuid: p.kuid })}
                width={1600} height={1010} loading="lazy" className="h-auto w-full rounded-card shadow-lift print:h-[54mm] print:w-[85.6mm] print:rounded-[3mm] print:shadow-none" />
            </figure>
          ))}
        </div>
      ) : null}
    </CoordinatorShell>
  );
}

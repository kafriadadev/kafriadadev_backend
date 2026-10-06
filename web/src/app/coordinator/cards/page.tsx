import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { CoordinatorNav } from "@/components/CoordinatorNav";
import { EmptyState } from "@/components/EmptyState";
import { Flash } from "@/components/Flash";
import { PageHead } from "@/components/PageHead";
import { Pager } from "@/components/Pager";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError, type CardBatch, getCardBatch, getMe } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { markPrintedAction } from "./actions";

export const metadata: Metadata = { title: "Print cards" };
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string =>
  Array.isArray(v) ? (v[0] ?? "") : (v ?? "");

/**
 * Bulk QR card printing (CRD-06): a registration drive into a stack of cards.
 *
 * A plain GET form filters by registration date and print status. Printing is the
 * browser's own — this page carries a print stylesheet that lays the cards out eight to
 * an A4 sheet at credit-card size — and there is a PDF of the same page for a browser
 * that cannot. A very large batch is paged, never built as one enormous document.
 */
export default async function CardsPage({ searchParams }: { searchParams: Promise<Search> }) {
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
      <div>
        <h1>Print cards</h1>
        <Flash variant="warn" title="No LGA to print for">
          <p>
            Choose a local government area on <a href="/coordinator">your dashboard</a> first.
          </p>
        </Flash>
      </div>
    );
  }

  let batch: CardBatch | null = null;
  let problem = one(params.error);
  try {
    batch = await getCardBatch(token, lga, { since, until, unprinted, page });
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403) problem = "You can only print cards for your own local government area.";
      else if (error.status === 422) problem = "Check the dates: use the form year-month-day.";
      else throw error;
    } else throw error;
  }

  const keep = (extra: Record<string, string> = {}) =>
    new URLSearchParams({ lga, since, until, unprinted: String(unprinted), page: String(page), ...extra });
  const pageLink = (p: number) => `/coordinator/cards?${keep({ page: String(p) })}`;
  const onPage = batch?.people.length ?? 0;
  const sheets = batch ? Math.ceil(onPage / batch.per_sheet) : 0;
  const marked = one(params.marked);

  return (
    <div>
      <CoordinatorNav current="/coordinator/cards" lga={lga} />
      <div>
        <PageHead
          eyebrow="Coordinator"
          title="Print cards"
          lede="Find the athletes whose cards you need, then print or download them."
          app
        />

        {problem ? (
          <Flash variant="bad" title="That did not work">
            <p>{problem}</p>
          </Flash>
        ) : null}
        {marked ? (
          <Flash variant="good" title="Recorded">
            <p>
              {marked === "1" ? "One card is" : `${marked} cards are`} now marked as printed.
            </p>
          </Flash>
        ) : null}

        <form method="get">
          <input type="hidden" name="lga" value={lga} />
          <div>
            <label htmlFor="since">Registered from</label>
            <input id="since" name="since" type="date" defaultValue={since} />
          </div>
          <div>
            <label htmlFor="until">Registered to</label>
            <input id="until" name="until" type="date" defaultValue={until} />
          </div>
          <div>
            <label htmlFor="unprinted">Show</label>
            <select id="unprinted" name="unprinted" defaultValue={String(unprinted)}>
              <option value="true">Not yet printed</option>
              <option value="false">All</option>
            </select>
          </div>
          <button type="submit">Find</button>
        </form>

        {batch && batch.total === 0 ? <EmptyState title="No athletes match" /> : null}

        {batch && batch.total > 0 ? (
          <div>
            <p>
              <strong>{batch.total}</strong> {batch.total === 1 ? "athlete" : "athletes"} &middot;{" "}
              {Math.ceil(batch.total / batch.per_sheet)} sheets of A4, {batch.per_sheet} cards per sheet.
              {batch.pages > 1 ? ` This is page ${batch.page} of ${batch.pages}: ${onPage} cards, ${sheets} sheets.` : ""}
            </p>
            <p>
              Use your browser&rsquo;s Print option (Ctrl+P). The cards print eight to a sheet at
              card size. If it cannot print from here, download the PDF instead.
            </p>
            <div>
              <a
                href={`/coordinator/cards/pdf?${keep()}`}
              >
                Download PDF
              </a>
              <form action={markPrintedAction}>
                <input type="hidden" name="lga" value={lga} />
                <input type="hidden" name="since" value={since} />
                <input type="hidden" name="until" value={until} />
                <input type="hidden" name="unprinted" value={String(unprinted)} />
                <input type="hidden" name="page" value={String(page)} />
                <input type="hidden" name="kuids" value={batch.people.map((p) => p.kuid).join(",")} />
                <SubmitButton pending="Recording…">
                  Mark these as printed
                </SubmitButton>
              </form>
            </div>
            <Pager
              page={batch.page}
              prev={batch.page > 1 ? pageLink(batch.page - 1) : null}
              next={batch.page < batch.pages ? pageLink(batch.page + 1) : null}
            />
          </div>
        ) : null}
      </div>

      {batch && batch.total > 0 ? (
        <div aria-label="Cards to print">
          {batch.people.map((p) => (
            <figure key={p.kuid}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`/card/${encodeURIComponent(p.kuid)}/card.png`}
                alt={`Card for ${p.full_name}, ${p.kuid}`}
                width={1600}
                height={1010}
              />
            </figure>
          ))}
        </div>
      ) : null}

    </div>
  );
}

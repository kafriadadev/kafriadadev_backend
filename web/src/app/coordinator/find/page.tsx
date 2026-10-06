import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconCreditCard, IconSearch, IconShieldCheck } from "@/components/icons";
import { EmptyNet, RaisedFlag } from "@/components/illustrations";
import { Button } from "@/components/ui/Button";
import { CoordinatorShell } from "@/components/ui/CoordinatorShell";
import { DataTable } from "@/components/ui/DataTable";
import { Field, Input } from "@/components/ui/Field";
import { PageHead } from "@/components/ui/Page";
import { EmptyState, PageState } from "@/components/ui/PageState";
import { Pager } from "@/components/ui/Pager";
import { Pill } from "@/components/ui/Pill";
import { ApiError, getMe, searchAthletes, type AthleteSearch } from "@/lib/api";
import { sessionToken } from "@/lib/session";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("find2"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

/**
 * Find an athlete (CRD-03): name (partial), ID or phone, inside one LGA. An
 * athlete outside it is simply "no results", never "not permitted", so the
 * answer cannot reveal who exists elsewhere. Plain GET, plain paging.
 */
export default async function FindAthletePage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("find2");
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  let own = "";
  let ownName = "";
  try {
    const me = await getMe(token);
    const grant = me.roles.find((r) => r.scope_kind === "lga");
    own = grant?.scope_id ?? "";
    ownName = grant?.scope_name ?? "";
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }
  const lga = one(params.lga) || own;
  const q = one(params.q).trim();
  const page = Math.max(Number.parseInt(one(params.page) || "1", 10) || 1, 1);
  if (!lga) {
    return (
      <PageState art={<RaisedFlag />} title={t("noLga")} action={<Button href="/coordinator" size="lg" block>{t("dashboard")}</Button>}>
        {t("noLgaText")}
      </PageState>
    );
  }

  let results: AthleteSearch | null = null;
  let denied = false;
  if (q) {
    try {
      results = await searchAthletes(token, lga, q, page);
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403 || error.status === 404) denied = true;
      else throw error;
    }
  }
  const link = (p: number) => `/coordinator/find?${new URLSearchParams({ lga, q, page: String(p) })}`;

  return (
    <CoordinatorShell current="find" lga={lga} token={token}>
      <PageHead eyebrow={t("eyebrow")} title={t("title")} lede={t("lede", { lga: lga === own && ownName ? ownName : t("thisLga") })} />
      <form method="get" role="search" className="flex flex-wrap items-end gap-3">
        <input type="hidden" name="lga" value={lga} />
        <Field name="q" label={t("label")} className="min-w-56 flex-1">
          {(a) => <Input {...a} required minLength={2} defaultValue={q} placeholder="Musa Ibrahim" />}
        </Field>
        <Button type="submit" size="lg" icon={<IconSearch size={20} aria-hidden="true" />}>{t("search")}</Button>
      </form>

      <div className="mt-8">
        {denied ? (
          <PageState art={<RaisedFlag />} title={t("noAccess")}>{t("noAccessText")}</PageState>
        ) : results && !results.people.length ? (
          <EmptyState art={<EmptyNet />} title={t("none")}>{t("noneText")}</EmptyState>
        ) : results ? (
          <>
            <DataTable
              caption={t("caption")}
              columns={[
                { key: "name", label: t("colName") },
                { key: "id", label: t("colId"), mono: true },
                { key: "status", label: t("colStatus") },
                { key: "actions", label: t("colActions"), align: "end" },
              ]}
              // The row key is the KUID, which is also what the ID column shows.
              rows={results.people.map((p) => ({
                id: p.kuid,
                name: (
                  <span>
                    <strong>{p.full_name}</strong>
                    {p.playing_position ? <span className="block text-xs text-muted">{p.playing_position}</span> : null}
                  </span>
                ),
                status: p.verified ? (
                  <Pill tone="good" icon={<IconShieldCheck size={16} aria-hidden="true" />}>{t("verified")}</Pill>
                ) : (
                  <Pill>{t("unverified")}</Pill>
                ),
                actions: (
                  <span className="inline-flex flex-wrap justify-end gap-2">
                    <a href={`/a/${encodeURIComponent(p.kuid)}`} className="inline-flex min-h-12 items-center font-bold">{t("profile")}</a>
                    {p.verified ? null : (
                      <Button href={`/assist-pay?${new URLSearchParams({ lga, kuid: p.kuid })}`} variant="secondary" icon={<IconCreditCard size={20} aria-hidden="true" />}>
                        {t("pay")}
                      </Button>
                    )}
                  </span>
                ),
              }))}
            />
            <Pager label={t("page", { n: page })} prev={page > 1 ? link(page - 1) : null} next={results.has_more ? link(page + 1) : null}
              labels={{ prev: t("prev"), next: t("next") }} />
          </>
        ) : null}
      </div>
    </CoordinatorShell>
  );
}

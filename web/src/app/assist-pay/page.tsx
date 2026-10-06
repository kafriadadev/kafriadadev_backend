import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconCash, IconLock } from "@/components/icons";
import { RaisedFlag } from "@/components/illustrations";
import { CoordinatorShell } from "@/components/ui/CoordinatorShell";
import { Checkbox, Field, Input } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { PageHead } from "@/components/ui/Page";
import { PageState } from "@/components/ui/PageState";
import { PlayerCard } from "@/components/ui/PlayerCard";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ApiError, getMe, getProfile, type Me, type PublicProfile } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { startAssistedPaymentAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("assist"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

/**
 * Assisted payment (CRD-04): for an athlete who cannot pay online. The
 * coordinator collects the cash, ticks that they have, and pays with their own
 * card; the ledger and the receipt land on the athlete. Whether this pairing is
 * allowed (own LGA, files ready, not already paid, inside today's caps) is the
 * API's to decide. From a search result this is one tick and one tap.
 */
export default async function AssistPayPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("assist");
  const tu = await getTranslations("ui");
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
  const lga = one(params.lga) || own;
  const kuid = one(params.kuid);
  const error = one(params.error);
  if (!lga) {
    return <PageState art={<RaisedFlag />} title={t("noLga")}>{t("noLgaText")}</PageState>;
  }
  const athlete: PublicProfile | null = kuid ? await getProfile(kuid).catch(() => null) : null;

  return (
    <CoordinatorShell current="pay" lga={lga} token={token}>
      <PageHead eyebrow={t("eyebrow")} title={t("title")} lede={t("lede")} />
      {error ? <Notice signal="red" title={t("error")} className="mb-6"><p>{error}</p></Notice> : null}

      <form action={startAssistedPaymentAction} noValidate className="space-y-6">
        <input type="hidden" name="lga" value={lga} />
        {athlete ? (
          <>
            <input type="hidden" name="kuid" value={athlete.kuid} />
            <PlayerCard
              size="sm"
              as="div"
              data={{ kuid: athlete.kuid, fullName: athlete.full_name, position: athlete.playing_position, lgaName: athlete.lga_name,
                stateName: athlete.state_name, year: athlete.registered_year, verified: athlete.is_verified }}
              labels={{ idLabel: tu("idLabel"), verified: tu("verified"), photoAlt: "", noPhoto: tu("noPhoto") }}
            />
          </>
        ) : (
          <Field name="kuid" label={t("kuid")} hint={t("kuidHint")}>
            {(a) => <Input {...a} required defaultValue={kuid} placeholder="KA-NG-JG-BKD-2026-000001" className="font-mono" />}
          </Field>
        )}

        <section aria-labelledby="about" className="rounded-card border-2 border-line-strong p-4">
          <h2 id="about" className="text-lg uppercase">{t("about")}</h2>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
            <dt className="text-muted">{t("collect")}</dt><dd className="font-bold">{t("fee")}</dd>
            <dt className="text-muted">{t("payWith")}</dt><dd className="font-bold">{t("yourCard")}</dd>
            <dt className="text-muted">{t("credited")}</dt><dd className="font-bold">{athlete?.full_name ?? "—"}</dd>
            <dt className="text-muted">{t("recorded")}</dt><dd className="font-bold">{t("assistedBy", { name: me.full_name })}</dd>
          </dl>
          <p className="mt-3 text-xs text-muted">{t("receipt")}</p>
        </section>

        <Checkbox name="cash_collected" value="yes" required>
          <span className="inline-flex items-start gap-2 font-bold"><IconCash size={20} className="mt-0.5 shrink-0" aria-hidden="true" />{t("collected")}</span>
        </Checkbox>
        <SubmitButton pendingLabel={t("pending")} icon={<IconLock size={20} aria-hidden="true" />}>{t("submit")}</SubmitButton>
        <p className="text-xs text-muted">{t("failedNote")}</p>
      </form>
    </CoordinatorShell>
  );
}

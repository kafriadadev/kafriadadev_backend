import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { IconInfoCircle } from "@/components/icons";
import { UnpluggedScoreboard } from "@/components/illustrations";
import { AthleteShell } from "@/components/ui/AthleteShell";
import { Button } from "@/components/ui/Button";
import { DataTable } from "@/components/ui/DataTable";
import { PageHead } from "@/components/ui/Page";
import { EmptyState } from "@/components/ui/PageState";
import { Pill, type Tone } from "@/components/ui/Pill";
import { ApiError, getMe, listPayments, type Me, type Payment } from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { sessionToken } from "@/lib/session";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("payments"))("title") };
}
export const dynamic = "force-dynamic";

const TONE: Record<Payment["state"], Tone> = { confirmed: "good", checking: "check", review: "warn", failed: "neutral" };
const stamp = (iso: string): string =>
  new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lagos" });

/**
 * My payments (ATH-04): every payment the athlete has started, newest first.
 * Read only: there is no action here, and that is the design. The statement
 * at the foot is regulatory: KAFRIADA NET is a record book, not a bank.
 */
export default async function PaymentsPage() {
  const t = await getTranslations("payments");
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  let me: Me;
  try {
    me = await getMe(token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirect("/sign-in?ended=1");
    throw error;
  }
  const payments = await listPayments(token);
  const purpose = t.raw("purpose") as Record<string, string>;

  return (
    <AthleteShell current="home" kuid={me.kuid}>
      <PageHead back={{ href: "/me", label: (await getTranslations("athleteNav"))("home") }} eyebrow={t("eyebrow")} title={t("title")} />
      <DataTable
        caption={t("caption")}
        columns={[
          { key: "payment", label: t("colPayment") },
          { key: "date", label: t("colDate") },
          { key: "status", label: t("colStatus") },
          { key: "amount", label: t("colAmount"), align: "end" },
          { key: "ref", label: t("colRef"), mono: true },
        ]}
        rows={payments.map((p) => ({
          id: p.reference,
          payment: <strong>{purpose[p.purpose] ?? p.purpose}</strong>,
          date: stamp(p.created_at),
          status: <Pill tone={TONE[p.state]}>{t(`state.${p.state}`)}</Pill>,
          amount: <strong className="scoreboard-digits">{formatNaira(p.amount_kobo)}</strong>,
          ref: <span className="text-xs">{p.reference}</span>,
        }))}
        empty={
          <EmptyState art={<UnpluggedScoreboard />} title={t("empty")} action={<Button href="/verify" variant="secondary">{t("emptyAction")}</Button>}>
            {t("emptyText")}
          </EmptyState>
        }
      />
      <p className="mt-6 flex gap-2 rounded-card bg-surface p-4 text-xs text-muted">
        <IconInfoCircle size={20} className="shrink-0" aria-hidden="true" />
        {t("notABank")}
      </p>
    </AthleteShell>
  );
}

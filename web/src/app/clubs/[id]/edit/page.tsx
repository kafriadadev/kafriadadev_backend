import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { ClubFields } from "@/components/ClubFields";
import { RaisedFlag } from "@/components/illustrations";
import { AthleteShell } from "@/components/ui/AthleteShell";
import { Button } from "@/components/ui/Button";
import { ErrorSummary } from "@/components/ui/Field";
import { PageHead } from "@/components/ui/Page";
import { PageState } from "@/components/ui/PageState";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ApiError, getClub, getMe, type ClubDashboard } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { updateClubAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("clubEdit"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;
const one = (v: string | string[] | undefined): string => (Array.isArray(v) ? (v[0] ?? "") : (v ?? ""));

/** Edit a club's record. Sport and area stay as registered. */
export default async function EditClubPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Search> }) {
  const t = await getTranslations("clubEdit");
  const { id } = await params;
  const query = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");

  let club: ClubDashboard;
  let kuid: string | null = null;
  try {
    [club, kuid] = await Promise.all([getClub(token, id), getMe(token).then((m) => m.kuid)]);
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401) redirect("/sign-in?ended=1");
      if (error.status === 403 || error.status === 404) {
        return (
          <PageState art={<RaisedFlag />} title={t("title")} action={<Button href="/me" size="lg" block>{(await getTranslations("club"))("back")}</Button>}>
            {t("noAccess")}
          </PageState>
        );
      }
    }
    throw error;
  }

  const error = one(query.error);
  const badField = one(query.field);
  // After a refusal the typed values come back in the address; otherwise the record.
  const edited = one(query.edited) === "1";
  const stored = (club.profile ?? {}) as Record<string, unknown>;
  const recordValue = (k: string): string => {
    if (k === "name") return club.name;
    if (k === "contact_phone") return club.contact_phone;
    if (k === "year_founded") return club.year_founded ? String(club.year_founded) : "";
    const v = stored[k];
    return v === null || v === undefined ? "" : String(v);
  };
  const get = (k: string): string => (edited ? one(query[k]) : recordValue(k));
  const all = (k: string): string[] => {
    if (!edited) return Array.isArray(stored[k]) ? (stored[k] as string[]) : [];
    const v = query[k];
    return Array.isArray(v) ? v : v ? [v] : [];
  };

  return (
    <AthleteShell current="clubs" kuid={kuid}>
      <PageHead back={{ href: `/clubs/${encodeURIComponent(id)}?tab=details`, label: club.name }} eyebrow={t("eyebrow")} title={t("title")} lede={t("lede")} />
      <div className="mb-8 empty:hidden">
        {error ? <ErrorSummary title={t("error")} errors={[{ field: badField || "name", message: error }]} /> : null}
      </div>
      <form action={updateClubAction} noValidate className="space-y-8">
        <input type="hidden" name="club" value={id} />
        <ClubFields values={{ get, all }} badField={badField} error={error} fixed={{ sport: club.sport, lga_name: club.lga_name }} />
        <SubmitButton pendingLabel={t("pending")}>{t("submit")}</SubmitButton>
      </form>
    </AthleteShell>
  );
}

import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { redirect } from "next/navigation";

import { ClubFields } from "@/components/ClubFields";
import { Checkbox, ErrorSummary } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import { Page, PageHead } from "@/components/ui/Page";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { ApiError, getMe, listLgas } from "@/lib/api";
import { sessionToken } from "@/lib/session";
import { registerClubAction } from "./actions";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("clubNew"))("title") };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;

/**
 * Staff register a club (CLB-01's manual-entry fallback): an administrator in
 * any area, an LGA coordinator in their own. Clubs normally sign themselves up
 * at /clubs/register; anyone else who lands here is sent there.
 */
export default async function NewClubPage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("clubNew");
  const ts = await getTranslations("clubSignup");
  const params = await searchParams;
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  const me = await getMe(token).catch((e) => {
    if (e instanceof ApiError && e.status === 401) redirect("/sign-in?ended=1");
    throw e;
  });
  const isAdmin = me.roles.some((r) => r.role === "super_admin");
  const coordinator = me.roles.find((r) => r.role === "lga_coordinator");
  if (!isAdmin && !coordinator) redirect("/clubs/register");

  const get = (k: string): string => {
    const v = params[k];
    return Array.isArray(v) ? (v[0] ?? "") : (v ?? "");
  };
  const all = (k: string): string[] => {
    const v = params[k];
    return Array.isArray(v) ? v : v ? [v] : [];
  };
  const error = get("error");
  const badField = get("field");
  const duplicate = get("duplicate") === "1";
  let open: { id: string; name: string }[] = [];
  try {
    open = (await listLgas()).filter((l) => l.is_open);
  } catch {
    // The selector is empty; the API still refuses an area that is not open.
  }

  return (
    <Page>
      <PageHead
        back={{ href: "/me", label: (await getTranslations("club"))("back") }}
        eyebrow={isAdmin ? t("eyebrowAdmin") : t("eyebrowCoordinator")}
        title={t("title")}
        lede={isAdmin ? t("ledeAdmin") : t("ledeCoordinator", { lga: coordinator?.scope_name ?? t("yourLga") })}
      />
      <div className="mb-8 empty:hidden">
        {error ? (
          duplicate ? (
            <Notice signal="yellow" title={ts("duplicate")}><p>{error} {ts("duplicateText")}</p></Notice>
          ) : (
            <ErrorSummary title={t("error")} errors={[{ field: badField || "name", message: error }]} />
          )
        ) : null}
      </div>
      <form action={registerClubAction} noValidate className="space-y-8">
        <ClubFields values={{ get, all }} badField={badField} error={error}
          lgas={isAdmin ? open : open.filter((l) => l.id === coordinator?.scope_id)} />
        {duplicate ? <Checkbox name="confirm_duplicate">{ts("duplicateBox")}</Checkbox> : null}
        <SubmitButton pendingLabel={t("pending")}>{t("submit")}</SubmitButton>
      </form>
    </Page>
  );
}

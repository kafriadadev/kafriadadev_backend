import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { IconRefresh } from "@/components/icons";
import { Iso } from "@/components/iso/Iso";
import { serverDown } from "@/components/iso/scenes";
import { Button } from "@/components/ui/Button";
import { PageState } from "@/components/ui/PageState";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("errors"))("unreachableTitle"), robots: { index: false } };
}
export const dynamic = "force-dynamic";

type Search = Record<string, string | string[] | undefined>;

/** Only a path on this site: never an address someone could put in the link. */
function safePath(raw: string | string[] | undefined): string {
  const value = Array.isArray(raw) ? raw[0] : raw;
  return value && value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/unavailable") ? value : "/";
}

/**
 * PUB-05, the API could not be reached. Server-rendered, so it shows with
 * JavaScript off (Next's error.tsx needs JavaScript to appear at all). Says
 * what is safe, offers one action back to the page they were on, and gives a
 * reference to read down the phone.
 */
export default async function UnavailablePage({ searchParams }: { searchParams: Promise<Search> }) {
  const t = await getTranslations("errors");
  const from = safePath((await searchParams).from);
  const reference = Math.random().toString(36).slice(2, 8).toUpperCase();
  console.error(JSON.stringify({ event: "api_unreachable_page", reference, from }));
  return (
    <PageState
      wideArt
      art={<Iso fig={serverDown()} name="server-down" />}
      title={t("unreachableTitle")}
      reference={reference}
      referenceHelp={t("refHelp")}
      action={<Button href={from} size="lg" block icon={<IconRefresh size={20} aria-hidden="true" />}>{t("retry")}</Button>}
      secondary={<a href="/">{t("home")}</a>}
    >
      {t("unreachableText")}
    </PageState>
  );
}

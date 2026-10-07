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

/**
 * PUB-05 when the phone is online but KAFRIADA NET did not answer. Static, so
 * the service worker can keep a copy for when the site itself is down; the
 * server-rendered /unavailable covers the API being down while the site is up.
 */
export default async function ServerUnreachablePage() {
  const t = await getTranslations("errors");
  return (
    <PageState wideArt art={<Iso fig={serverDown()} name="server-down" />} title={t("unreachableTitle")}
      action={<Button href="/me" data-retry="" size="lg" block icon={<IconRefresh size={20} aria-hidden="true" />}>{t("retry")}</Button>}
      secondary={<a href="/">{t("home")}</a>}>
      {t("unreachableText")}
    </PageState>
  );
}

import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { IconRefresh } from "@/components/icons";
import { NoSignal } from "@/components/illustrations";
import { Button } from "@/components/ui/Button";
import { PageState } from "@/components/ui/PageState";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getTranslations("errors"))("offlineTitle"), robots: { index: false } };
}

/**
 * PUB-05, offline. Static, so the service worker can keep a copy and show it
 * when a phone loses its connection mid-visit. `data-retry` lets the service
 * worker point Try again at the page that failed.
 */
export default async function OfflinePage() {
  const t = await getTranslations("errors");
  return (
    <PageState art={<NoSignal />} title={t("offlineTitle")}
      action={<Button href="/me" data-retry="" size="lg" block icon={<IconRefresh size={20} aria-hidden="true" />}>{t("retry")}</Button>}>
      {t("offlineText")}
    </PageState>
  );
}

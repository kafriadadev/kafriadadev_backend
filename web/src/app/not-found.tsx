import { getTranslations } from "next-intl/server";

import { IconSearch } from "@/components/icons";
import { EmptyNet } from "@/components/illustrations";
import { Button } from "@/components/ui/Button";
import { PageState } from "@/components/ui/PageState";

/** PUB-05, not found: no alarm, always a way forward. */
export default async function NotFound() {
  const t = await getTranslations();
  return (
    <PageState
      art={<EmptyNet />}
      title={t("errors.notFoundTitle")}
      action={<Button href="/find" size="lg" block icon={<IconSearch size={20} aria-hidden="true" />}>{t("nav.findId")}</Button>}
      secondary={<a href="/">{t("errors.home")}</a>}
    >
      {t("errors.notFoundText")}
    </PageState>
  );
}

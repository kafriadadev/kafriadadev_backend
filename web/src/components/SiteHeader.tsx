import { getTranslations } from "next-intl/server";
import { IconSearch, IconShirtSport, IconUser } from "@/components/icons";
import { TopBar } from "@/components/ui/Navigation";

/** The public top bar. Reads no cookie, so cached pages stay cached. */
export async function SiteHeader() {
  const t = await getTranslations("nav");
  const tb = await getTranslations("brand");
  return (
    <TopBar
      homeLabel={tb("home")}
      links={[
        { href: "/find", label: t("findId"), icon: <IconSearch size={20} aria-hidden="true" /> },
        { href: "/clubs/register", label: t("registerClub"), icon: <IconShirtSport size={20} aria-hidden="true" />, publicOnly: true },
        { href: "/me", label: t("myAccount"), icon: <IconUser size={20} aria-hidden="true" /> },
      ]}
      action={{ href: "/register", label: t("registerFree") }}
      menu={{ label: t("menu"), title: t("menuTitle"), close: t("close") }}
    />
  );
}

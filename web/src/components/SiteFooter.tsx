import { getTranslations } from "next-intl/server";
import { Footer } from "@/components/ui/Navigation";

export async function SiteFooter() {
  const t = await getTranslations("nav");
  const tb = await getTranslations("brand");
  return (
    <Footer
      tagline={tb("tagline")}
      label={t("footer")}
      links={[
        { href: "/find", label: t("findId") },
        { href: "/register", label: t("registerAthlete") },
        { href: "/clubs/register", label: t("registerClub") },
        { href: "/privacy", label: t("privacy") },
      ]}
    />
  );
}

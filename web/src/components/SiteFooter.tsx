import { getTranslations } from "next-intl/server";

/** The footer on every page. Bare until the Phase 2 redesign. */
export async function SiteFooter() {
  const t = await getTranslations();
  return (
    <footer>
      <p>{t("brand.name")} · {t("brand.tagline")}</p>
      <nav aria-label={t("nav.footer")}>
        <ul>
          <li><a href="/find">{t("nav.findId")}</a></li>
          <li><a href="/register">{t("nav.registerAthlete")}</a></li>
          <li><a href="/clubs/register">{t("nav.registerClub")}</a></li>
          <li><a href="/privacy">{t("nav.privacy")}</a></li>
        </ul>
      </nav>
    </footer>
  );
}

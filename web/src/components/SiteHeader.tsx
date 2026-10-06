import { getTranslations } from "next-intl/server";
import { Logo } from "./brand/Logo";

/**
 * The header on every page. Reads no cookie, so the public profile and the
 * landing page can still be cached. Bare until the Phase 2 TopBar.
 */
export async function SiteHeader() {
  const t = await getTranslations();
  return (
    <header>
      <p>
        <a href="/" aria-label={t("brand.home")}>
          <Logo className="h-8 w-auto text-text" />
        </a>
      </p>
      <nav aria-label={t("nav.main")}>
        <ul>
          <li><a href="/find">{t("nav.findId")}</a></li>
          <li><a href="/clubs/register">{t("nav.registerClub")}</a></li>
          <li><a href="/me">{t("nav.myAccount")}</a></li>
          <li><a href="/register">{t("nav.registerFree")}</a></li>
        </ul>
      </nav>
    </header>
  );
}

import Head from "next/head";
import { createTranslator } from "next-intl";

import { IconSearch, IconShirtSport, IconUser } from "@/components/icons";
import { Footer, TopBar } from "@/components/ui/Navigation";
import { DEFAULT_LOCALE } from "@/i18n/request";
import messages from "../../messages/en.json";

/** The translator for a Pages Router page: the same strings file, read on the server. */
export const translator = () => createTranslator({ locale: DEFAULT_LOCALE, messages });

/**
 * The frame of a zero-JavaScript public page on the Pages Router: the same top
 * bar, skip link and footer the App Router layout draws, and the same head.
 * `title` is the page's own name; the template adds the product name.
 */
export function PublicDocument({
  title,
  description,
  noindex,
  head,
  mainClassName,
  children,
}: {
  title?: string;
  description?: string;
  noindex?: boolean;
  /** Extra head elements, such as Open Graph tags. */
  head?: React.ReactNode;
  mainClassName?: string;
  children: React.ReactNode;
}) {
  const t = translator();
  return (
    <>
      <Head>
        <title>{title ? t("meta.titleTemplate").replace("%s", title) : t("meta.title")}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" content="#0EAD2C" />
        <meta name="description" content={description ?? t("meta.description")} />
        {noindex ? <meta name="robots" content="noindex" /> : null}
        {head}
      </Head>
      <a href="#main" className="sr-only z-50 rounded-pill bg-boot px-4 py-3 font-bold text-chalk focus:not-sr-only focus:fixed focus:left-4 focus:top-4">
        {t("nav.skip")}
      </a>
      <TopBar
        homeLabel={t("brand.home")}
        links={[
          { href: "/find", label: t("nav.findId"), icon: <IconSearch size={20} aria-hidden="true" /> },
          { href: "/clubs/register", label: t("nav.registerClub"), icon: <IconShirtSport size={20} aria-hidden="true" />, publicOnly: true },
          { href: "/me", label: t("nav.myAccount"), icon: <IconUser size={20} aria-hidden="true" /> },
        ]}
        action={{ href: "/register", label: t("nav.registerFree") }}
        menu={{ label: t("nav.menu"), title: t("nav.menuTitle"), close: t("nav.close") }}
      />
      <main id="main" className={mainClassName}>{children}</main>
      <Footer
        tagline={t("brand.tagline")}
        label={t("nav.footer")}
        links={[
          { href: "/find", label: t("nav.findId") },
          { href: "/register", label: t("nav.registerAthlete") },
          { href: "/clubs/register", label: t("nav.registerClub") },
          { href: "/privacy", label: t("nav.privacy") },
        ]}
      />
    </>
  );
}

import { getTranslations } from "next-intl/server";

import { IconHome, IconIdBadge2, IconShieldCheck, IconShirtSport, IconUser } from "@/components/icons";
import { TabBar } from "./Navigation";

export type AthleteTab = "home" | "card" | "clubs" | "verify" | "me";

/**
 * The athlete's screens: their own tab bar (bottom on phones, a rail on wide
 * screens) beside the content. Accounts with no athlete record get the
 * content alone.
 */
export async function AthleteShell({ current, kuid, children }: { current: AthleteTab; kuid: string | null; children: React.ReactNode }) {
  if (!kuid) return <div className="mx-auto w-full max-w-measure px-4 pb-16 pt-8 sm:px-6">{children}</div>;
  const t = await getTranslations("athleteNav");
  const icon = (I: typeof IconHome) => <I size={22} aria-hidden="true" />;
  const items = [
    { key: "home", href: "/me", label: t("home"), icon: icon(IconHome) },
    { key: "card", href: `/card/${encodeURIComponent(kuid)}`, label: t("card"), icon: icon(IconIdBadge2) },
    { key: "clubs", href: "/clubs", label: t("clubs"), icon: icon(IconShirtSport) },
    { key: "verify", href: "/verify", label: t("verify"), icon: icon(IconShieldCheck) },
    { key: "me", href: "/details", label: t("me"), icon: icon(IconUser) },
  ];
  const currentHref = items.find((i) => i.key === current)?.href ?? "/me";
  return (
    <div className="mx-auto w-full max-w-5xl px-4 pt-8 sm:px-6 md:flex md:gap-10">
      <div className="min-w-0 flex-1 pb-16 md:max-w-measure">{children}</div>
      {/* After the content in the page, so the phone spacer sits at the bottom;
          first on wide screens, as the rail. */}
      <div className="md:sticky md:top-24 md:order-first md:self-start">
        <TabBar label={t("label")} current={currentHref} items={items} />
      </div>
    </div>
  );
}

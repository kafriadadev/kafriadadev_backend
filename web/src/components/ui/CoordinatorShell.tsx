import { getTranslations } from "next-intl/server";

import { IconCash, IconCreditCard, IconHome, IconPrinter, IconSearch, IconVarScreen } from "@/components/icons";
import { getCoordinatorDashboard } from "@/lib/api";
import { formatNaira } from "@/lib/money";
import { TabBar } from "./Navigation";

export type CoordinatorTab = "today" | "queue" | "find" | "pay" | "cards";

/**
 * The coordinator's screens: their own tabs (bottom on phones, a rail on a
 * tablet or laptop) and, for an LGA coordinator, today's cash total pinned at
 * the top of every screen: in a hall with cash changing hands it must always
 * be in sight. Tabs are plain links carrying the LGA.
 */
export async function CoordinatorShell({
  current,
  lga,
  token,
  children,
}: {
  current: CoordinatorTab;
  lga: string;
  token: string;
  children: React.ReactNode;
}) {
  const t = await getTranslations("coordNav");
  const q = `?lga=${encodeURIComponent(lga)}`;
  const icon = (I: React.ComponentType<{ size?: number; "aria-hidden"?: boolean | "true" }>) => <I size={22} aria-hidden="true" />;
  const items = [
    { key: "today", href: `/coordinator${q}`, label: t("today"), icon: icon(IconHome) },
    { key: "queue", href: `/review${q}`, label: t("queue"), icon: icon(IconVarScreen) },
    { key: "find", href: `/coordinator/find${q}`, label: t("find"), icon: icon(IconSearch) },
    { key: "pay", href: `/assist-pay${q}`, label: t("pay"), icon: icon(IconCreditCard) },
    { key: "cards", href: `/coordinator/cards${q}`, label: t("cards"), icon: icon(IconPrinter) },
  ];
  const d = await getCoordinatorDashboard(token, lga).catch(() => null);

  return (
    <div data-signed-in="" className="mx-auto w-full max-w-wide px-4 pt-6 sm:px-6 md:flex md:gap-10">
      <div className="min-w-0 flex-1 pb-16">
        {d?.can_assist ? (
          <p className="mb-6 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-card bg-scoreboard px-4 py-3 text-scoreboard-text print:hidden">
            <span className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-[0.1em]">
              <IconCash size={20} aria-hidden="true" />
              {t("cash")}
            </span>
            <span className="font-display text-2xl font-extrabold italic text-scoreboard-accent scoreboard-digits">{formatNaira(d.collected_kobo)}</span>
            <span className="w-full text-xs">
              {t("cashOf", { count: d.collected_count, limit: d.limit_count, amount: formatNaira(d.limit_kobo) })}
            </span>
          </p>
        ) : null}
        {children}
      </div>
      <div className="print:hidden md:sticky md:top-24 md:order-first md:self-start">
        <TabBar label={t("label")} current={items.find((i) => i.key === current)?.href ?? items[0].href} items={items} />
      </div>
    </div>
  );
}

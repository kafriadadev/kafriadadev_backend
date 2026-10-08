import { Logo } from "@/components/brand/Logo";
import { IconMenu2 } from "@/components/icons";
import { cn } from "@/lib/cn";
import { buttonClass } from "./Button";
import { Sheet } from "./Overlay";

export type NavItem = { href: string; label: string; icon?: React.ReactNode; publicOnly?: boolean };

/**
 * The top bar on every screen. Reads no cookie, so cached pages stay cached.
 * On a phone the secondary links move into a sheet (no script needed).
 */
export function TopBar({
  homeLabel,
  links,
  action,
  pinned,
  menu,
}: {
  homeLabel: string;
  /** Secondary links: inline on wide screens, in the menu sheet on phones. */
  links: NavItem[];
  /** The one call to action, for example "Register free". */
  action?: NavItem;
  /** Always visible, for example a coordinator's cash total. */
  pinned?: React.ReactNode;
  menu: { label: string; title: string; close: string };
}) {
  return (
    <header data-site-chrome="" className="sticky top-0 z-30 border-b border-line print:hidden bg-[color-mix(in_srgb,var(--bg)_92%,transparent)] backdrop-blur">
      <div className="mx-auto flex h-16 max-w-wide items-center gap-3 px-4">
        <a href="/" aria-label={homeLabel} className="mr-auto shrink-0">
          <Logo className="h-8 w-auto text-text" />
        </a>
        {pinned ? <div className="shrink-0">{pinned}</div> : null}
        <nav aria-label={menu.title} className="hidden items-center gap-1 md:flex">
          {links.map((l) => (
            <a key={l.href} href={l.href} data-public-only={l.publicOnly ? "" : undefined} className="inline-flex min-h-12 items-center gap-2 rounded-pill px-3 font-bold text-text no-underline hover:bg-surface-2">
              {l.icon}
              {l.label}
            </a>
          ))}
        </nav>
        {action ? (
          <span data-public-only="" className="hidden sm:inline-flex">
            <a href={action.href} className={buttonClass({ size: "md", className: "min-h-10 whitespace-nowrap px-4 text-base" })}>
              {action.label}
            </a>
          </span>
        ) : null}
        <Sheet
          className="md:hidden"
          trigger={
            <>
              <IconMenu2 aria-hidden="true" />
              <span>{menu.label}</span>
            </>
          }
          title={menu.title}
          closeLabel={menu.close}
        >
          <ul className="space-y-1">
            {links.map((l) => (
              <li key={l.href} data-public-only={l.publicOnly ? "" : undefined}>
                <a href={l.href} className="flex min-h-12 items-center gap-3 rounded-card px-3 text-md font-bold text-text no-underline hover:bg-surface-2">
                  {l.icon}
                  {l.label}
                </a>
              </li>
            ))}
          </ul>
          {action ? (
            <a href={action.href} data-public-only="" className={buttonClass({ size: "lg", block: true, className: "mt-4" })}>
              {action.label}
            </a>
          ) : null}
        </Sheet>
      </div>
    </header>
  );
}

/**
 * A role's own navigation: a bottom tab bar on phones (the thumb zone), a
 * left rail on wide screens. Plain links; the current one is marked.
 */
export function TabBar({ items, current, label }: { items: NavItem[]; current: string; label: string }) {
  return (
    <>
      <nav
        aria-label={label}
        className={cn(
          "fixed inset-x-0 bottom-0 z-30 border-t border-line bg-bg pb-[env(safe-area-inset-bottom)]",
          "md:static md:w-56 md:shrink-0 md:border-0 md:bg-transparent md:pb-0",
        )}
      >
        <ul className="grid auto-cols-fr grid-flow-col md:flex md:flex-col md:gap-1">
          {items.map((it) => {
            const on = it.href === current;
            return (
              <li key={it.href}>
                <a
                  href={it.href}
                  aria-current={on ? "page" : undefined}
                  className={cn(
                    "flex min-h-16 flex-col items-center justify-center gap-0.5 px-1 text-xs font-bold no-underline",
                    "md:min-h-12 md:flex-row md:justify-start md:gap-3 md:rounded-pill md:px-4 md:text-base",
                    on ? "text-text md:bg-pitch md:text-on-pitch" : "text-muted hover:text-text md:hover:bg-surface-2",
                  )}
                >
                  <span className={cn("grid h-7 place-items-center rounded-pill px-3 md:h-auto md:px-0", on && "bg-pitch text-on-pitch md:bg-transparent")}>
                    {it.icon}
                  </span>
                  <span className="truncate">{it.label}</span>
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
      {/* Keeps the last content clear of the fixed bar on phones. */}
      <div className="h-20 md:hidden" aria-hidden="true" />
    </>
  );
}

export function Footer({ tagline, links, label }: { tagline: string; links: NavItem[]; label: string }) {
  return (
    <footer data-site-chrome="" className="mt-16 border-t border-line bg-surface print:hidden">
      <div className="mx-auto flex max-w-wide flex-col gap-6 px-4 py-10 md:flex-row md:items-start md:justify-between">
        <div>
          <Logo className="h-8 w-auto text-text" />
          <p className="mt-2 text-xs text-muted">{tagline}</p>
        </div>
        <nav aria-label={label}>
          <ul className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
            {links.map((l) => (
              <li key={l.href}>
                <a href={l.href} className="inline-flex min-h-12 items-center font-bold">{l.label}</a>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </footer>
  );
}

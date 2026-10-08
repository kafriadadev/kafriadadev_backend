import { signOutAction } from "@/app/me/actions";
import { Logo } from "./brand/Logo";
import {
  IconCash, IconFileText, IconHome, IconLock, IconLogout, IconMapPin, IconMenu2, IconRefresh, IconShieldCheck,
  IconShirtSport, IconUser, IconUsersGroup, IconX,
} from "./icons";
import { cn } from "@/lib/cn";

const GROUPS = [
  {
    label: null,
    links: [{ href: "/admin", label: "Overview", Icon: IconHome }],
  },
  {
    label: "People and clubs",
    links: [
      { href: "/admin/users", label: "Users and roles", Icon: IconUsersGroup },
      { href: "/admin/clubs", label: "Clubs", Icon: IconShirtSport },
      { href: "/admin/club-verification", label: "Club reviews", Icon: IconShieldCheck },
    ],
  },
  {
    label: "Verification and money",
    links: [
      { href: "/admin/revoke", label: "Withdraw a verification", Icon: IconRefresh },
      { href: "/admin/reversal", label: "Record a refund", Icon: IconCash },
    ],
  },
  {
    label: "Programme",
    links: [
      { href: "/admin/rollout", label: "LGA rollout", Icon: IconMapPin },
      { href: "/admin/data-requests", label: "Data requests", Icon: IconLock },
      { href: "/admin/audit", label: "Audit log", Icon: IconFileText },
    ],
  },
] as const;

function NavLinks({ current }: { current: string }) {
  return (
    <div className="space-y-6">
      {GROUPS.map((g) => (
        <div key={g.label ?? "top"}>
          {g.label ? <p className="mb-1.5 px-3 text-xs font-bold uppercase kc-group text-muted">{g.label}</p> : null}
          <ul className="space-y-0.5">
            {g.links.map(({ href, label, Icon }) => {
              const on = href === current;
              return (
                <li key={href}>
                  <a
                    href={href}
                    aria-current={on ? "page" : undefined}
                    className={cn(
                      "relative flex min-h-10 items-center gap-3 kc-round px-3 text-sm font-bold no-underline transition-colors",
                      on
                        ? "kc-nav-on"
                        : "text-muted hover:bg-surface-2 hover:text-text",
                    )}
                  >
                    <Icon size={18} className={on ? "text-link" : undefined} aria-hidden="true" />
                    {label}
                  </a>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

function AccountLinks() {
  return (
    <div className="space-y-0.5 border-t border-line pt-3">
      <a href="/me" className="flex min-h-10 items-center gap-3 kc-round px-3 text-sm font-bold text-muted no-underline hover:bg-surface-2 hover:text-text">
        <IconUser size={18} aria-hidden="true" />
        My account
      </a>
      <form action={signOutAction}>
        <button type="submit" className="flex min-h-10 w-full items-center gap-3 kc-round px-3 text-left text-sm font-bold text-muted hover:bg-surface-2 hover:text-text">
          <IconLogout size={18} aria-hidden="true" />
          Sign out
        </button>
      </form>
    </div>
  );
}

/**
 * The administrator console's frame, an application rather than a page of the
 * public site: on a laptop a permanent sidebar down the left edge, with the
 * sections, your account and sign out, that stays put while the page scrolls;
 * on a phone a fixed top bar whose menu opens the same sections (a <details>,
 * so it needs no script). The public site header and footer step aside while
 * `data-console` is on the page (globals.css). `data-console` also turns on the
 * console's base styles for native form controls and tables.
 */
export function AdminShell({ current, children }: { current: string; children: React.ReactNode }) {
  return (
    <div data-console="" data-signed-in="" className="min-h-dvh bg-bg">
      {/* Laptop and up: the permanent sidebar. */}
      <aside aria-label="Administrator" className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col border-r border-line bg-surface lg:flex print:hidden">
        <div className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-line px-5">
          <a href="/admin" className="no-underline" aria-label="KAFRIADA NET administrator console">
            <Logo className="h-9 w-auto text-text" />
          </a>
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs font-bold text-muted">Console</span>
        </div>
        <nav aria-label="Console sections" className="min-h-0 flex-1 overflow-y-auto px-3 py-5">
          <NavLinks current={current} />
        </nav>
        <div className="shrink-0 px-3 pb-4">
          <AccountLinks />
        </div>
      </aside>

      {/* Phone and tablet: a fixed top bar and a menu. */}
      <div className="sticky top-0 z-40 flex h-14 items-center justify-between border-b border-line kc-topbar px-4 backdrop-blur lg:hidden print:hidden">
        <a href="/admin" className="no-underline" aria-label="KAFRIADA NET administrator console">
          <Logo className="h-8 w-auto text-text" />
        </a>
        <details className="group">
          <summary className="inline-flex min-h-10 cursor-pointer list-none items-center gap-2 kc-round border border-line-strong px-3 text-sm font-bold kc-summary">
            <IconMenu2 size={18} className="group-open:hidden" aria-hidden="true" />
            <IconX size={18} className="hidden group-open:block" aria-hidden="true" />
            <span className="group-open:hidden">Menu</span>
            <span className="hidden group-open:inline">Close</span>
          </summary>
          <div className="fixed inset-x-0 bottom-0 top-14 z-40 overflow-y-auto border-t border-line bg-surface px-3 py-5 motion-fade">
            <NavLinks current={current} />
            <div className="mt-6">
              <AccountLinks />
            </div>
          </div>
        </details>
      </div>

      <div className="lg:pl-64">
        <div data-console-main="" className="mx-auto w-full max-w-6xl space-y-6 px-4 pb-16 pt-8 sm:px-8">{children}</div>
      </div>
    </div>
  );
}

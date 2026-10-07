import {
  IconCash, IconFileText, IconHome, IconLock, IconMapPin, IconRefresh, IconShieldCheck, IconShirtSport, IconUsersGroup,
} from "./icons";
import { cn } from "@/lib/cn";

const LINKS = [
  { href: "/admin", label: "Overview", Icon: IconHome },
  { href: "/admin/users", label: "Users and roles", Icon: IconUsersGroup },
  { href: "/admin/clubs", label: "Clubs", Icon: IconShirtSport },
  { href: "/admin/club-verification", label: "Club reviews", Icon: IconShieldCheck },
  { href: "/admin/audit", label: "Audit log", Icon: IconFileText },
  { href: "/admin/revoke", label: "Withdraw a verification", Icon: IconRefresh },
  { href: "/admin/reversal", label: "Record a refund", Icon: IconCash },
  { href: "/admin/rollout", label: "LGA rollout", Icon: IconMapPin },
  { href: "/admin/data-requests", label: "Data requests", Icon: IconLock },
] as const;

/**
 * The administrator console: calm and dense, built for a laptop. A sidebar on
 * wide screens, a wrapping row of links on a phone (admin is read-only there in
 * practice). `data-console` turns on the console's base styles for native form
 * controls and tables (globals.css), which these screens use directly.
 */
export function AdminShell({ current, children }: { current: string; children: React.ReactNode }) {
  return (
    <div data-console="" data-signed-in="" className="mx-auto w-full max-w-wide px-4 pb-16 pt-6 sm:px-6 lg:flex lg:gap-10">
      <nav aria-label="Administrator" className="mb-6 lg:sticky lg:top-24 lg:mb-0 lg:w-64 lg:shrink-0 lg:self-start">
        <p className="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-muted">Administrator</p>
        <ul className="flex flex-wrap gap-1 lg:flex-col">
          {LINKS.map(({ href, label, Icon }) => {
            const on = href === current;
            return (
              <li key={href}>
                <a
                  href={href}
                  aria-current={on ? "page" : undefined}
                  className={cn(
                    "flex min-h-12 items-center gap-3 rounded-pill px-4 font-bold no-underline",
                    on ? "bg-pitch text-on-pitch" : "text-text hover:bg-surface-2",
                  )}
                >
                  <Icon size={20} aria-hidden="true" />
                  {label}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="min-w-0 flex-1 space-y-6">{children}</div>
    </div>
  );
}

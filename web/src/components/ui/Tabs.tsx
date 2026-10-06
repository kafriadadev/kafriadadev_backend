import { cn } from "@/lib/cn";

/** Sections of one screen, as plain links. The current one is marked, not linked. */
export function Tabs({ items, current, label, className }: { items: { href: string; label: string; count?: number }[]; current: string; label: string; className?: string }) {
  return (
    <nav aria-label={label} className={cn("border-b-2 border-line", className)}>
      <ul className="-mb-0.5 flex flex-wrap gap-x-1">
        {items.map((it) => {
          const on = it.href === current;
          return (
            <li key={it.href}>
              <a
                href={it.href}
                aria-current={on ? "page" : undefined}
                className={cn(
                  "inline-flex min-h-12 items-center gap-2 border-b-[3px] px-3 font-bold no-underline",
                  on ? "border-pitch text-text" : "border-transparent text-muted hover:text-text",
                )}
              >
                {it.label}
                {it.count ? <span className="rounded-pill bg-surface-2 px-2 text-xs text-text">{it.count}</span> : null}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

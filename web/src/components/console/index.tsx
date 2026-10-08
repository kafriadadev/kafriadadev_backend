/*
 * The administrator console's own components: calm, dense and plain, built for a
 * laptop. The athlete screens speak in the kit's voice (condensed italic capitals,
 * big pill buttons); the console is a tool, so it speaks in the body face, at a
 * smaller size, with compact controls. Same tokens, same colours, light and dark.
 * Every piece is server-rendered and works with JavaScript off.
 */
import { cn } from "@/lib/cn";

/** The page title, what the page is for, and its main actions, on one line when there is room. */
export function ConsoleHeader({ title, description, actions, back }: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  back?: { href: string; label: string };
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b border-line pb-5">
      <div className="min-w-0 max-w-3xl">
        {back ? (
          <a href={back.href} className="mb-2 inline-flex text-sm font-bold text-muted no-underline hover:text-text">
            ← {back.label}
          </a>
        ) : null}
        <h1 className="font-body kc-title font-bold not-italic normal-case leading-tight tracking-tight">{title}</h1>
        {description ? <p className="mt-1.5 text-sm text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

/** A panel: an optional heading row with actions, then its content. */
export function Card({ title, description, actions, children, className, flush = false, id }: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  /** No inner padding, for a table that runs edge to edge. */
  flush?: boolean;
  id?: string;
}) {
  return (
    <section data-card="" id={id} aria-labelledby={id && title ? `${id}-title` : undefined} className={cn("overflow-clip kc-round border border-line bg-bg kc-shadow", className)}>
      {title || actions ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <div className="min-w-0">
            {title ? <h2 id={id ? `${id}-title` : undefined} className="font-body text-base font-bold not-italic normal-case">{title}</h2> : null}
            {description ? <p className="mt-0.5 text-sm text-muted">{description}</p> : null}
          </div>
          {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      <div className={flush ? undefined : "p-5"}>{children}</div>
    </section>
  );
}

export type BadgeTone = "neutral" | "good" | "warn" | "bad" | "info";

const BADGE: Record<BadgeTone, { box: string; dot: string }> = {
  neutral: { box: "bg-surface-2", dot: "bg-muted" },
  good: { box: "kc-tint-good", dot: "bg-pitch" },
  warn: { box: "kc-tint-warn", dot: "kc-dot-warn" },
  bad: { box: "kc-tint-bad", dot: "kc-dot-bad" },
  info: { box: "kc-tint-info", dot: "kc-dot-info" },
};

/** A short status word. The dot's colour repeats the word; it never replaces it. */
export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: React.ReactNode }) {
  const b = BADGE[tone];
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-bold text-text", b.box)}>
      <span className={cn("size-1.5 rounded-full", b.dot)} aria-hidden="true" />
      {children}
    </span>
  );
}

/** A filter as a segmented control of plain links. The current choice is marked, not linked. */
export function Segmented({ label, items, current }: {
  label: string;
  items: { href: string; label: string; count?: number }[];
  current: string;
}) {
  return (
    <nav aria-label={label}>
      <ul className="inline-flex flex-wrap gap-1 kc-round bg-surface-2 p-1">
        {items.map((it) => {
          const on = it.href === current;
          return (
            <li key={it.href}>
              <a
                href={it.href}
                aria-current={on ? "page" : undefined}
                className={cn(
                  "inline-flex min-h-9 items-center gap-2 kc-round-inner px-3 text-sm font-bold no-underline",
                  on ? "bg-bg text-text kc-shadow-on" : "text-muted hover:text-text",
                )}
              >
                {it.label}
                {it.count !== undefined ? (
                  <span className={cn("rounded-full px-1.5 text-xs", on ? "bg-surface-2" : "bg-bg")}>{it.count}</span>
                ) : null}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** A figure that matters: label, value, and a line of context. */
export function Metric({ label, value, sub, tone, href }: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "good" | "warn" | "bad";
  href?: string;
}) {
  const body = (
    <>
      <span className="flex items-center justify-between gap-2 text-sm font-bold text-muted">
        {label}
        {tone ? <span className={cn("size-2 rounded-full", tone === "good" ? "bg-pitch" : tone === "warn" ? "kc-dot-warn" : "bg-danger")} aria-hidden="true" /> : null}
      </span>
      <span className="mt-2 block whitespace-nowrap font-body kc-figure font-bold leading-none tracking-tight scoreboard-digits">{value}</span>
      {sub ? <span className="mt-2 block text-xs text-muted">{sub}</span> : null}
    </>
  );
  const cls = "kaf-stat block kc-round border border-line bg-bg p-4 text-text no-underline";
  return href ? <a href={href} className={cn(cls, "transition-colors hover:border-line-strong")}>{body}</a> : <div className={cls}>{body}</div>;
}

/** Metrics side by side, as many as fit. */
export function MetricGrid({ children }: { children: React.ReactNode }) {
  return <div className="kc-grid-metrics">{children}</div>;
}

/** Nothing to show: one line of what that means, and an optional way on. */
export function ConsoleEmpty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="kc-round border border-dashed border-line-strong px-6 py-10 text-center">
      <p className="font-bold">{title}</p>
      {children ? <div className="mt-1 text-sm text-muted">{children}</div> : null}
    </div>
  );
}

/** A label and a value, for a record's details. */
export function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-bold text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm font-bold">{children}</dd>
    </div>
  );
}

export function Details({ children }: { children: React.ReactNode }) {
  return <dl className="kc-grid-details">{children}</dl>;
}

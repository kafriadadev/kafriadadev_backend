import { cn } from "@/lib/cn";

/**
 * The KUID in a scoreboard strip. An ID never breaks across lines: the size
 * follows the strip's width (container query), so a 24-character ID fits a
 * 320px phone and grows on a desktop.
 */
export function KuidStrip({ kuid, label, className, plate = false }: { kuid: string; label?: string; className?: string; plate?: boolean }) {
  return (
    <div
      className={cn(
        "@container rounded-input px-3 py-2",
        plate ? "bg-plate-strip text-plate-strip-text" : "bg-scoreboard text-scoreboard-text",
        className,
      )}
    >
      {label ? <p className="text-xs font-bold uppercase tracking-[0.18em] opacity-85">{label}</p> : null}
      <p className="whitespace-nowrap font-mono text-[clamp(0.75rem,6.1cqi,1.75rem)] leading-tight scoreboard-digits">{kuid}</p>
    </div>
  );
}

/** The numbers that matter: dark panel, tabular digits. */
export function Scoreboard({ items, className }: { items: { label: string; value: React.ReactNode; accent?: boolean }[]; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-[repeat(auto-fit,minmax(6.25rem,1fr))] gap-px overflow-hidden rounded-card bg-[color-mix(in_srgb,var(--scoreboard-text)_18%,transparent)]", className)}>
      {items.map((it) => (
        <div key={it.label} className="bg-scoreboard p-4 text-scoreboard-text">
          <dt className="text-xs font-bold uppercase tracking-[0.14em] opacity-85">{it.label}</dt>
          <dd className={cn("mt-1 font-display text-3xl font-extrabold italic leading-none scoreboard-digits", it.accent && "text-scoreboard-accent")}>
            {it.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

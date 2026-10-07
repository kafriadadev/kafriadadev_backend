import { cn } from "@/lib/cn";

const TONE = { good: "border-pitch", warn: "border-[var(--yellow-card)]", bad: "border-danger" } as const;

/** One number on a dashboard: a scoreboard tile, its edge coloured by tone. */
export function Stat({ label, value, sub, tone, href }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: "good" | "warn" | "bad"; href?: string;
}) {
  const body = (
    <>
      <span className="block text-xs font-bold uppercase tracking-[0.08em] [overflow-wrap:normal] opacity-90">{label}</span>
      <span className="mt-1 block whitespace-nowrap font-display text-2xl font-extrabold italic leading-none scoreboard-digits">{value}</span>
      {sub ? <span className="mt-1 block text-xs opacity-90">{sub}</span> : null}
    </>
  );
  const cls = cn("kaf-stat block rounded-card border-l-[6px] border-scoreboard bg-scoreboard p-4 text-scoreboard-text no-underline", tone && TONE[tone]);
  return href ? <a href={href} className={cn(cls, "hover:opacity-90")}>{body}</a> : <div className={cls}>{body}</div>;
}

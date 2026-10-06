import { cn } from "@/lib/cn";

export type Column = { key: string; label: string; align?: "start" | "end"; mono?: boolean };

/**
 * Dense, calm data: a sticky header on wide screens; under 640px each row
 * becomes a card with its labels, so nothing scrolls sideways.
 */
export function DataTable({
  caption,
  columns,
  rows,
  empty,
  className,
}: {
  caption: string;
  columns: Column[];
  rows: (Record<string, React.ReactNode> & { id: string })[];
  empty?: React.ReactNode;
  className?: string;
}) {
  if (!rows.length && empty) return <>{empty}</>;
  return (
    // overflow-clip, not hidden: hidden makes this box the sticky header's scroll
    // container, and the header's 64px offset would then sit over the first row.
    <div className={cn("overflow-clip rounded-card border border-line", className)}>
      <table className="w-full border-collapse text-left">
        <caption className="sr-only">{caption}</caption>
        <thead className="sticky top-16 hidden bg-surface-2 text-xs uppercase tracking-[0.1em] text-muted sm:table-header-group">
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={cn("px-4 py-3 font-bold", c.align === "end" && "text-right")}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="block border-t border-line p-3 first:border-t-0 sm:table-row sm:p-0 sm:hover:bg-surface">
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={cn(
                    "flex flex-wrap justify-between gap-x-4 gap-y-1 py-1 sm:table-cell sm:px-4 sm:py-3",
                    c.align === "end" && "sm:text-right",
                    c.mono && "font-mono scoreboard-digits",
                  )}
                >
                  <span className="text-xs font-bold uppercase tracking-[0.1em] text-muted sm:hidden" aria-hidden="true">
                    {c.label}
                  </span>
                  <span className={cn("min-w-0 text-right sm:text-[inherit]", c.mono && "whitespace-nowrap")}>{r[c.key]}</span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

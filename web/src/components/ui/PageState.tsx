import { cn } from "@/lib/cn";
import { RefChip } from "./RefChip";
import { Spinner } from "./Spinner";

/**
 * A whole-screen state: not found, not allowed, signed out, too many
 * attempts, unreachable, offline, server error. Illustration, headline, one
 * sentence, one main action, one quiet link, the reference chip.
 */
export function PageState({
  art,
  title,
  children,
  action,
  secondary,
  reference,
  referenceHelp,
  className,
}: {
  art: React.ReactNode;
  title: React.ReactNode;
  children: React.ReactNode;
  action?: React.ReactNode;
  secondary?: React.ReactNode;
  reference?: string;
  referenceHelp?: string;
  className?: string;
}) {
  return (
    <section className={cn("mx-auto flex max-w-measure flex-col items-center px-4 py-12 text-center", className)}>
      <div className="w-48 text-text motion-rise">{art}</div>
      <h1 className="mt-6 text-2xl">{title}</h1>
      <div className="mt-3 max-w-prose text-md text-muted">{children}</div>
      {action ? <div className="mt-8 w-full max-w-xs">{action}</div> : null}
      {secondary ? <div className="mt-3">{secondary}</div> : null}
      {reference ? (
        <div className="mt-8 flex justify-center">
          <RefChip code={reference} help={referenceHelp} />
        </div>
      ) : null}
    </section>
  );
}

/** Nothing here yet: what is missing, one sentence, and the button that fills it. */
export function EmptyState({
  art,
  title,
  children,
  action,
  className,
}: {
  art: React.ReactNode;
  title: React.ReactNode;
  children?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center rounded-card border-2 border-dashed border-line-strong px-4 py-8 text-center", className)}>
      <div className="w-32 text-muted">{art}</div>
      <p className="mt-4 font-display text-xl font-extrabold uppercase italic">{title}</p>
      {children ? <div className="mt-2 max-w-prose text-muted">{children}</div> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

/** Over three seconds: the shape of the coming content, in pitch lines. */
export function Skeleton({ lines = 3, className, label }: { lines?: number; className?: string; label: string }) {
  return (
    <div role="status" aria-label={label} className={cn("space-y-3", className)}>
      <div className="grid h-24 place-items-center rounded-card border-2 border-dashed border-line-strong">
        <Spinner size={44} />
      </div>
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="h-3 animate-pulse rounded-pill bg-surface-2" style={{ width: `${92 - i * 18}%` }} />
      ))}
    </div>
  );
}

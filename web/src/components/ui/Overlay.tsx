import { IconCheck, IconX } from "@/components/icons";
import { cn } from "@/lib/cn";

/**
 * A small confirmation ("Copied", "Saved"). Status only, never an error that
 * needs action, and never the only way to learn something happened.
 */
export function Toast({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div role="status" className={cn("motion-rise inline-flex items-center gap-2 rounded-pill bg-boot px-4 py-3 font-bold text-chalk shadow-float", className)}>
      <IconCheck size={20} className="text-pitch" aria-hidden="true" />
      {children}
    </div>
  );
}

/**
 * A bottom sheet built on <details>: the browser opens and closes it, no
 * script involved. The summary is the trigger; while the sheet is open the
 * same summary becomes the Close button pinned in the thumb zone, because
 * without script nothing else can close a <details>.
 */
export function Sheet({
  trigger,
  title,
  closeLabel,
  children,
  className,
}: {
  trigger: React.ReactNode;
  title: string;
  closeLabel: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <details className={cn("group", className)}>
      <summary
        className={cn(
          "inline-flex min-h-12 cursor-pointer list-none items-center justify-center gap-2 whitespace-nowrap rounded-pill px-3 font-bold text-link hover:bg-surface-2 [&::-webkit-details-marker]:hidden",
          "group-open:fixed group-open:inset-x-4 group-open:bottom-4 group-open:z-[60] group-open:bg-surface-2 group-open:text-text",
          "sm:group-open:left-1/2 sm:group-open:right-auto sm:group-open:w-[30rem] sm:group-open:-translate-x-1/2",
        )}
      >
        <span className="inline-flex items-center gap-2 group-open:hidden">{trigger}</span>
        <span className="hidden items-center gap-2 group-open:inline-flex">
          <IconX size={20} aria-hidden="true" />
          {closeLabel}
        </span>
      </summary>
      <div className="fixed inset-0 z-40 bg-[color-mix(in_srgb,var(--boot)_45%,transparent)]" aria-hidden="true" />
      <div
        role="dialog"
        aria-label={title}
        className="fixed inset-x-0 bottom-0 z-50 max-h-[85vh] overflow-y-auto rounded-t-[var(--radius-card)] bg-bg p-4 pb-24 shadow-float motion-rise sm:inset-x-auto sm:left-1/2 sm:w-[32rem] sm:-translate-x-1/2"
      >
        <div className="mx-auto mb-3 h-1.5 w-12 rounded-pill bg-line-strong" aria-hidden="true" />
        <p className="mb-3 font-display text-xl font-extrabold uppercase italic">{title}</p>
        {children}
      </div>
    </details>
  );
}

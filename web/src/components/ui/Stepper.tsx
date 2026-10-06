import { IconBallFootball, IconCheck } from "@/components/icons";
import { cn } from "@/lib/cn";

/**
 * The run: progress along a touchline. Markers for each step, the ball on the
 * current one. Plain markup, so with JavaScript off it simply shows where you
 * are.
 */
export function Stepper({
  steps,
  current,
  label,
  progressText,
}: {
  steps: string[];
  /** Zero-based index of the step in progress. */
  current: number;
  label: string;
  /** For example "Step 2 of 3". */
  progressText: string;
}) {
  const pct = steps.length > 1 ? (current / (steps.length - 1)) * 100 : 0;
  return (
    <div className="space-y-3">
      <p className="text-xs font-bold uppercase tracking-[0.14em] text-muted">{progressText}</p>
      <div className="relative mx-4 h-8">
        <span className="absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 bg-line-strong" aria-hidden="true" />
        <span
          className="absolute left-0 top-1/2 h-1 -translate-y-1/2 rounded-pill bg-pitch transition-[width] duration-[var(--dur-move)] ease-kick"
          style={{ width: `${pct}%` }}
          aria-hidden="true"
        />
        <span
          className="absolute top-1/2 grid size-8 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-bg text-text transition-[left] duration-[var(--dur-move)] ease-bounce"
          style={{ left: `${pct}%` }}
          aria-hidden="true"
        >
          <IconBallFootball size={28} stroke={1.75} />
        </span>
      </div>
      <ol aria-label={label} className="grid gap-2" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}>
        {steps.map((s, i) => {
          const done = i < current;
          const now = i === current;
          return (
            <li
              key={s}
              aria-current={now ? "step" : undefined}
              className={cn("flex flex-col items-center gap-1 text-center text-xs", now ? "font-bold text-text" : done ? "text-text" : "text-muted")}
            >
              <span
                className={cn(
                  "grid size-6 place-items-center rounded-full border-2",
                  done ? "border-pitch bg-pitch text-on-pitch" : now ? "border-text" : "border-line-strong",
                )}
                aria-hidden="true"
              >
                {done ? <IconCheck size={16} stroke={3} /> : <span className="text-xs leading-none">{i + 1}</span>}
              </span>
              {s}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

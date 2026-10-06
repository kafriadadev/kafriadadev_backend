import { IconRedCard } from "@/components/icons";
import { cn } from "@/lib/cn";

/*
 * Choose a position by tapping it on a pitch. Underneath it is a group of
 * ordinary radio buttons, so it works with JavaScript off, and with CSS off it
 * is still a plain list. The values are the API's football positions.
 *
 * Attacking upward; x and y are percentages of the half-pitch.
 */
const SPOTS: { value: string; x: number; y: number }[] = [
  { value: "Striker", x: 50, y: 9 },
  { value: "Winger", x: 83, y: 21 },
  { value: "Attacking midfielder", x: 50, y: 28 },
  { value: "Central midfielder", x: 50, y: 45 },
  { value: "Defensive midfielder", x: 50, y: 61 },
  { value: "Full-back", x: 17, y: 71 },
  { value: "Centre-back", x: 50, y: 77 },
  { value: "Goalkeeper", x: 50, y: 92 },
];

export function PositionPicker({
  name = "playing_position",
  legend,
  value,
  error,
  labels,
}: {
  name?: string;
  legend: React.ReactNode;
  value?: string | null;
  error?: string | null;
  /** Display name for each API value, in the reader's language. */
  labels: Record<string, string>;
}) {
  const errorId = error ? `${name}-error` : undefined;
  return (
    <fieldset className="border-0 p-0" aria-describedby={errorId}>
      <legend className="mb-3 font-bold">{legend}</legend>
      <div
        className={cn(
          "relative mx-auto aspect-[3/4] w-full max-w-sm overflow-hidden rounded-card bg-[var(--pitch-deep)] turf-stripes",
          error && "ring-4 ring-danger",
        )}
      >
        <svg viewBox="0 0 300 400" className="absolute inset-0 size-full" aria-hidden="true" preserveAspectRatio="none">
          <g fill="none" stroke="var(--chalk)" strokeOpacity=".55" strokeWidth="2">
            <rect x="10" y="10" width="280" height="380" />
            <path d="M10 390H290" />
            <path d="M80 10V70H220V10M115 10V32H185V10" />
            <path d="M80 390V330H220V390M115 390V368H185V390" />
            <path d="M118 330A40 40 0 0 1 182 330M118 70A40 40 0 0 0 182 70" />
            <path d="M10 200H290" />
            <circle cx="150" cy="200" r="40" />
          </g>
        </svg>
        {SPOTS.map((s, i) => {
          const id = `${name}-${i}`;
          return (
            <label
              key={s.value}
              htmlFor={id}
              className="absolute flex -translate-x-1/2 -translate-y-1/2 cursor-pointer flex-col items-center gap-1 text-center"
              style={{ left: `${s.x}%`, top: `${s.y}%` }}
            >
              <input
                type="radio"
                id={id}
                name={name}
                value={s.value}
                defaultChecked={value === s.value}
                required={i === 0}
                className="peer sr-only"
              />
              <span
                className={cn(
                  "grid size-8 place-items-center rounded-full border-[3px] border-chalk bg-[color-mix(in_srgb,var(--boot)_35%,transparent)]",
                  "transition-transform duration-[var(--dur-quick)] ease-bounce",
                  "peer-checked:scale-110 peer-checked:border-boot peer-checked:bg-[var(--yellow-card)]",
                  "peer-focus-visible:outline peer-focus-visible:outline-3 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-chalk",
                )}
                aria-hidden="true"
              />
              <span className="whitespace-nowrap rounded-pill bg-boot px-2 py-0.5 text-xs font-bold leading-tight text-chalk peer-checked:bg-[var(--yellow-card)] peer-checked:text-boot">
                {labels[s.value] ?? s.value}
              </span>
            </label>
          );
        })}
      </div>
      {error ? (
        <p id={errorId} className="mt-2 flex items-start gap-2 font-bold text-danger">
          <IconRedCard size={20} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      ) : null}
    </fieldset>
  );
}

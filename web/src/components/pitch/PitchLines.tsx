/*
 * The pitch as the grid: chalk lines drawn in SVG, coloured by --chalk-line
 * (logo green on light, chalk white under floodlights). Never a photo of
 * grass. `motion-draw` chalks the lines in with CSS alone: a long dash slid
 * into place, measured in screen pixels because the stroke does not scale.
 * Without CSS animation the lines are simply there.
 */

type LineProps = { className?: string; draw?: boolean };

const stroke = {
  fill: "none",
  stroke: "var(--chalk-line)",
  strokeWidth: 2,
  vectorEffect: "non-scaling-stroke" as const,
  strokeLinecap: "round" as const,
};

/** A full pitch, 105 × 68 metres, the real proportions. */
export function Pitch({ className, draw }: LineProps) {
  const d = draw ? "motion-draw" : undefined;
  return (
    <svg viewBox="-2 -2 109 72" className={className} aria-hidden="true" focusable="false">
      <rect x="0" y="0" width="105" height="68" rx="0.5" className={d} {...stroke} />
      <path d="M52.5 0V68" className={d} {...stroke} />
      <circle cx="52.5" cy="34" r="9.15" className={d} {...stroke} />
      <path d="M0 13.84H16.5V54.16H0M105 13.84H88.5V54.16H105" className={d} {...stroke} />
      <path d="M0 24.84H5.5V43.16H0M105 24.84H99.5V43.16H105" className={d} {...stroke} />
      <path d="M16.5 26.69A9.15 9.15 0 0 1 16.5 41.31M88.5 26.69A9.15 9.15 0 0 0 88.5 41.31" className={d} {...stroke} />
      <circle cx="52.5" cy="34" r="0.6" fill="var(--chalk-line)" />
      <circle cx="11" cy="34" r="0.6" fill="var(--chalk-line)" />
      <circle cx="94" cy="34" r="0.6" fill="var(--chalk-line)" />
    </svg>
  );
}

/** The centre circle, for behind hero content. */
export function CentreCircle({ className, draw }: LineProps) {
  const d = draw ? "motion-draw" : undefined;
  return (
    <svg viewBox="0 0 200 200" className={className} aria-hidden="true" focusable="false">
      <circle cx="100" cy="100" r="70" className={d} {...stroke} />
      <circle cx="100" cy="100" r="3" fill="var(--chalk-line)" />
    </svg>
  );
}

/** The halfway line between sections: a rule with the centre spot. */
export function HalfwayLine({ className }: { className?: string }) {
  return (
    <div role="separator" className={`flex items-center gap-0 ${className ?? ""}`}>
      <span className="h-0.5 flex-1 bg-[var(--chalk-line)]" />
      <span className="size-6 rounded-full border-2 border-[var(--chalk-line)]" />
      <span className="h-0.5 flex-1 bg-[var(--chalk-line)]" />
    </div>
  );
}

/** The penalty arc that frames a primary button from above. */
export function PenaltyArc({ className, draw }: LineProps) {
  return (
    <svg viewBox="0 0 120 36" className={className} aria-hidden="true" focusable="false">
      <path d="M8 34A60 60 0 0 1 112 34" className={draw ? "motion-draw" : undefined} {...stroke} />
    </svg>
  );
}

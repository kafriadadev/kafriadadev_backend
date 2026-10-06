import { Figure } from "@/components/brand/Logo";
import { cn } from "@/lib/cn";

/**
 * The KAFRIADA NET spinner: the logo's running figure rising and settling, as
 * it does in the logo, inside a chalk-line centre circle that keeps being
 * drawn. CSS only, so it costs no JavaScript and shows wherever the page does.
 * Under reduced motion the ring stands still and the figure only pulses.
 *
 * Decorative by default; give it a `label` where it is the only sign that
 * something is happening.
 */
export function Spinner({ size = 48, label, className }: { size?: number; label?: string; className?: string }) {
  return (
    <span
      role={label ? "status" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      // The figure's dark body takes the surrounding text colour, so it suits any background.
      className={cn("relative inline-grid shrink-0 place-items-center", className)}
      style={{ width: size, height: size }}
    >
      {/* The centre circle: a faint full ring, and a green arc travelling round it. */}
      <svg viewBox="0 0 48 48" className="absolute inset-0 size-full" focusable="false">
        <circle cx="24" cy="24" r="21" fill="none" stroke="var(--line-strong)" strokeOpacity=".35" strokeWidth="2.5" />
        <circle
          cx="24" cy="24" r="21" fill="none" stroke="var(--spinner-arc, var(--pitch))" strokeWidth="3" strokeLinecap="round"
          strokeDasharray="34 98" className="spin-ring"
        />
      </svg>
      {/* The figure, rising on each beat like the logo's arms-up celebration. */}
      <svg viewBox="32 113 431 476" className="spin-figure relative h-[58%] w-auto" focusable="false">
        <Figure />
      </svg>
    </span>
  );
}

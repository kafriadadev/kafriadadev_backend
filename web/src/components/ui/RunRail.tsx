import { IconBallFootball } from "@/components/icons";

/**
 * "The run" (AUT-01): a touchline along the top of a long form, one marker per
 * part. The ball moves on to the next marker as each part becomes complete, and
 * a finished part's marker turns green. Plain CSS (`:has(:valid)` in
 * globals.css, `.run-rail`), so it works with JavaScript off; a browser without
 * `:has` shows the ball at the start. It repeats the parts' own headings, so it
 * is hidden from screen readers.
 *
 * `parts` are the form's three fieldsets, with ids part-0, part-1 and part-2.
 */
export function RunRail({ parts }: { parts: { id: string; label: string }[] }) {
  return (
    <div className="run-rail sticky top-16 z-20 -mx-4 bg-[color-mix(in_srgb,var(--bg)_94%,transparent)] px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6" aria-hidden="true">
      <div className="relative h-6">
        <div className="absolute inset-x-3 top-[11px] h-0.5 bg-line-strong" />
        <div className="run-fill absolute left-3 top-[11px] h-0.5 bg-pitch" />
        {parts.map((p, i) => (
          <span
            key={p.id}
            data-part={i}
            className="run-dot absolute top-0 size-6 -translate-x-1/2 rounded-full border-2 border-line-strong bg-bg"
          />
        ))}
        <span className="run-ball absolute top-0 grid size-6 -translate-x-1/2 place-items-center rounded-full bg-bg text-text">
          <IconBallFootball size={24} />
        </span>
      </div>
      <ol className="mt-1 grid grid-cols-3 text-xs font-bold uppercase tracking-[0.08em] text-muted">
        {parts.map((p, i) => (
          <li key={p.id} className={i === 0 ? "text-left" : i === parts.length - 1 ? "text-right" : "text-center"}>{p.label}</li>
        ))}
      </ol>
    </div>
  );
}

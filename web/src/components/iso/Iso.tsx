import { cn } from "@/lib/cn";
import type { Figure } from "./figures.ts";

/**
 * An isometric figure, drawn on the server: plain SVG in the page, so it works
 * with JavaScript off and in Opera Mini. It repeats what the words around it
 * already say, so it is hidden from screen readers. /iso.js replays its motion
 * when it scrolls into view or is tapped, and links `data-key` parts to the
 * list items that name them.
 */
export function Iso({ fig, className, name, style }: { fig: Figure; className?: string; name?: string; style?: React.CSSProperties }) {
  return (
    <svg
      className={cn("iso is-play", className)}
      viewBox={fig.viewBox}
      data-iso={name}
      style={style}
      aria-hidden="true"
      focusable="false"
      dangerouslySetInnerHTML={{ __html: fig.body }}
    />
  );
}

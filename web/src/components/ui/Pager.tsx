import { IconArrowLeft, IconArrowRight } from "@/components/icons";
import { buttonClass } from "./Button";

/** Previous / next for a paged list. Plain links, so it works without JavaScript. */
export function Pager({ label, prev, next, labels }: { label: string; prev?: string | null; next?: string | null; labels: { prev: string; next: string } }) {
  if (!prev && !next) return null;
  return (
    <nav aria-label={label} className="mt-6 flex items-center justify-between gap-3">
      {prev ? (
        <a href={prev} className={buttonClass({ variant: "secondary" })}><IconArrowLeft size={20} aria-hidden="true" />{labels.prev}</a>
      ) : <span />}
      <span className="text-xs font-bold text-muted">{label}</span>
      {next ? (
        <a href={next} className={buttonClass({ variant: "secondary" })}>{labels.next}<IconArrowRight size={20} aria-hidden="true" /></a>
      ) : <span />}
    </nav>
  );
}

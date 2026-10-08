import { buttonClass } from "./ui/Button";

/** Previous and next pages of a console list, as plain links. */
export function Pager({ page, prev, next }: { page: number; prev?: string | null; next?: string | null }) {
  if (!prev && !next) return null;
  return (
    <nav aria-label={`Page ${page}`} className="mt-4 flex items-center justify-between gap-3 text-sm">
      {prev ? <a href={prev} className={buttonClass({ variant: "secondary", size: "sm" })}>Previous</a> : <span />}
      <span className="text-muted">Page {page}</span>
      {next ? <a href={next} className={buttonClass({ variant: "secondary", size: "sm" })}>Next</a> : <span />}
    </nav>
  );
}

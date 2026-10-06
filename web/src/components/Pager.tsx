/** Previous / next for a paged list. Plain links, so it works without JavaScript. */
export function Pager({ page, prev, next }: { page: number; prev?: string | null; next?: string | null }) {
  if (!prev && !next) return null;
  return (
    <nav aria-label="Pages">
      {prev ? <a href={prev}>Previous</a> : null} <span>Page {page}</span>{" "}
      {next ? <a href={next}>Next</a> : null}
    </nav>
  );
}

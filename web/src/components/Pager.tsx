/** Previous / next for a paged list. Plain links, so it works without JavaScript. */
export function Pager({ page, prev, next }: { page: number; prev?: string | null; next?: string | null }) {
  if (!prev && !next) return null;
  return (
    <nav className="pager" aria-label="Pages">
      {prev ? <a href={prev}>&larr; Previous</a> : <span />}
      <span>Page {page}</span>
      {next ? <a href={next}>Next &rarr;</a> : <span />}
    </nav>
  );
}

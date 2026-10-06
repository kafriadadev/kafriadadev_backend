/**
 * The header on every page. Reads no cookie, so the public profile and the
 * landing page can still be cached.
 */
export function SiteHeader() {
  return (
    <header>
      <p><a href="/">KAFRIADA NET</a></p>
      <nav aria-label="Main">
        <ul>
          <li><a href="/find">Look up an ID</a></li>
          <li><a href="/clubs/register">Register a club</a></li>
          <li><a href="/me">My account</a></li>
          <li><a href="/register">Register free</a></li>
        </ul>
      </nav>
    </header>
  );
}

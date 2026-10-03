/** The footer on every page: where to look something up, and who issues the ID. */
export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="wrap site-footer__inner">
        <p>KAFRIADA · Kowa Guru Technology · Federation of Nigerian Sports</p>
        <nav aria-label="Footer">
          <a href="/find">Look up an ID</a>
          <a href="/register">Register as an athlete</a>
          <a href="/clubs/register">Register a club</a>
          <a href="/privacy">Privacy notice</a>
        </nav>
      </div>
    </footer>
  );
}

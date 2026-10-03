import Link from "next/link";

const LINKS = [
  { href: "/find", label: "Look up an ID" },
  { href: "/clubs/register", label: "Register a club" },
  { href: "/me", label: "My account" },
] as const;

/**
 * The header on every page. Static on purpose: it reads no cookie, so the
 * public profile and the landing page can still be cached. "My account" goes
 * to /me, which sends anyone not signed in to the sign-in screen.
 */
export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="wrap site-header__bar">
        <Link href="/" className="brand" aria-label="KAFRIADA home">
          <span className="wordmark">KAF<span>RIADA</span></span>
          <span className="brand__meta">Jigawa State · Pilot</span>
        </Link>

        <nav className="nav-inline" aria-label="Main">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href} className="nav-link">{l.label}</a>
          ))}
          <a href="/register" className="btn btn--primary btn--sm">Register free</a>
        </nav>

        <details className="nav-menu">
          <summary>Menu</summary>
          <nav className="nav-menu__panel" aria-label="Main">
            {LINKS.map((l) => (
              <a key={l.href} href={l.href} className="nav-link">{l.label}</a>
            ))}
            <a href="/register" className="btn btn--primary btn--block">Register free</a>
          </nav>
        </details>
      </div>
    </header>
  );
}

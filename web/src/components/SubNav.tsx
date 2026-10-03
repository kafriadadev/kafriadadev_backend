export type NavLink = { href: string; label: string };

/** Tabs for a section of the product. The current page is marked, not linked. */
export function SubNav({
  links,
  current,
  label,
  heading,
}: {
  links: readonly NavLink[];
  current: string;
  label: string;
  /** Shown above the links when they sit in a sidebar. */
  heading?: string;
}) {
  return (
    <nav className="subnav" aria-label={label}>
      {heading ? <span className="subnav__label">{heading}</span> : null}
      {links.map((l) =>
        l.href === current ? (
          <strong key={l.href} aria-current="page">{l.label}</strong>
        ) : (
          <a key={l.href} href={l.href}>{l.label}</a>
        ),
      )}
    </nav>
  );
}

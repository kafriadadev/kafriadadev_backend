export type NavLink = { href: string; label: string };

/** Links across a section of the product. The current page is marked, not linked. */
export function SubNav({
  links,
  current,
  label,
  heading,
}: {
  links: readonly NavLink[];
  current: string;
  label: string;
  heading?: string;
}) {
  return (
    <nav aria-label={label}>
      {heading ? <p>{heading}</p> : null}
      <ul>
        {links.map((l) => (
          <li key={l.href}>
            {l.href === current ? <strong aria-current="page">{l.label}</strong> : <a href={l.href}>{l.label}</a>}
          </li>
        ))}
      </ul>
    </nav>
  );
}

const LINKS = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/users", label: "Users and roles" },
  { href: "/admin/clubs", label: "Clubs" },
  { href: "/admin/club-verification", label: "Club reviews" },
  { href: "/admin/audit", label: "Audit log" },
  { href: "/admin/revoke", label: "Withdraw a verification" },
  { href: "/admin/reversal", label: "Record a refund" },
] as const;

/** The administrator console's navigation: plain links, current page not a link. */
export function AdminNav({ current }: { current: string }) {
  return (
    <nav
      aria-label="Administrator"
      style={{ display: "flex", gap: "var(--s4)", flexWrap: "wrap", marginBottom: "var(--s3)" }}
    >
      {LINKS.map((l) =>
        l.href === current ? (
          <strong key={l.href} aria-current="page">{l.label}</strong>
        ) : (
          <a key={l.href} href={l.href}>{l.label}</a>
        ),
      )}
    </nav>
  );
}

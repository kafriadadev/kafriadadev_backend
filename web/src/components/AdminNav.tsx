import { SubNav } from "./SubNav";

const LINKS = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/users", label: "Users and roles" },
  { href: "/admin/clubs", label: "Clubs" },
  { href: "/admin/club-verification", label: "Club reviews" },
  { href: "/admin/audit", label: "Audit log" },
  { href: "/admin/revoke", label: "Withdraw a verification" },
  { href: "/admin/reversal", label: "Record a refund" },
] as const;

/** The administrator console's sections. */
export function AdminShell({ current, children }: { current: string; children: React.ReactNode }) {
  return (
    <div>
      <SubNav links={LINKS} current={current} label="Administrator" heading="Administrator" />
      <div>{children}</div>
    </div>
  );
}

import { SubNav } from "./SubNav";

/** The coordinator's sections, carrying the LGA being worked on. */
export function CoordinatorNav({ current, lga }: { current: string; lga: string }) {
  const q = `?lga=${encodeURIComponent(lga)}`;
  const links = [
    { href: "/coordinator", label: "Today" },
    { href: "/review", label: "Review verifications" },
    { href: "/coordinator/find", label: "Find an athlete" },
    { href: "/coordinator/cards", label: "Print cards" },
    { href: "/assist-pay", label: "Pay for an athlete" },
  ];
  return (
    <SubNav
      links={links.map((l) => ({ href: l.href + q, label: l.label }))}
      current={current + q}
      label="Coordinator"
    />
  );
}

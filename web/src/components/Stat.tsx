/** One number on a dashboard, with what it counts and an optional second line. */
export function Stat({
  label,
  value,
  sub,
  tone,
  href,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "good" | "warn" | "bad";
  href?: string;
}) {
  const className = tone ? `stat stat--${tone}` : "stat";
  const body = (
    <>
      <p className="stat__label">{label}</p>
      <p className="stat__value">{value}</p>
      {sub ? <p className="stat__sub">{sub}</p> : null}
    </>
  );
  return href ? <a href={href} className={className}>{body}</a> : <div className={className}>{body}</div>;
}

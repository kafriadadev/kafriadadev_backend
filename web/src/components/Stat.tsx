/** One number on a dashboard, with what it counts and an optional second line. */
export function Stat({
  label,
  value,
  sub,
  href,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "good" | "warn" | "bad";
  href?: string;
}) {
  const body = (
    <>
      {label}: <strong>{value}</strong>
      {sub ? <> ({sub})</> : null}
    </>
  );
  return <p>{href ? <a href={href}>{body}</a> : body}</p>;
}

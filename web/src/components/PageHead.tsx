/** The top of a screen: where you are, what it is, and what you can do here. */
export function PageHead({
  eyebrow,
  title,
  lede,
  actions,
  back,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  lede?: React.ReactNode;
  actions?: React.ReactNode;
  back?: { href: string; label: string };
  /** Accepted for compatibility; unused until the redesign. */
  app?: boolean;
}) {
  return (
    <header>
      {back ? <p><a href={back.href}>{back.label}</a></p> : null}
      {eyebrow ? <p>{eyebrow}</p> : null}
      <h1>{title}</h1>
      {lede ? <p>{lede}</p> : null}
      {actions ? <div>{actions}</div> : null}
    </header>
  );
}

/** The top of a screen: where you are, what it is, and what you can do here. */
export function PageHead({
  eyebrow,
  title,
  lede,
  actions,
  back,
  app = false,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  lede?: React.ReactNode;
  actions?: React.ReactNode;
  back?: { href: string; label: string };
  /** A working screen (dashboard, list): a smaller title. */
  app?: boolean;
}) {
  return (
    <header className={app ? "page-head page-head--app" : "page-head"}>
      {back ? <a href={back.href} className="back">{back.label}</a> : null}
      <div className="row-between">
        <div>
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h1>{title}</h1>
          {lede ? <p className="lede">{lede}</p> : null}
        </div>
        {actions ? <div className="cluster">{actions}</div> : null}
      </div>
    </header>
  );
}

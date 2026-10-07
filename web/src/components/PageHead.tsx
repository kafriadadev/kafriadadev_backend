import { PageHead as Head } from "./ui/Page";

/** The old PageHead on the new one; `actions` sit beside the heading. */
export function PageHead({ eyebrow, title, lede, actions, back }: {
  eyebrow?: React.ReactNode; title: React.ReactNode; lede?: React.ReactNode; actions?: React.ReactNode;
  back?: { href: string; label: string }; app?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <Head eyebrow={eyebrow} title={title} lede={lede} back={back} className="mb-6" />
      {actions ? <div className="mb-6 flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

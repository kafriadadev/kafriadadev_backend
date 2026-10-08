import { ConsoleHeader } from "./console";

/** The administrator console's page heading. Only the console uses this adapter. */
export function PageHead({ title, lede, actions, back }: {
  eyebrow?: React.ReactNode; title: React.ReactNode; lede?: React.ReactNode; actions?: React.ReactNode;
  back?: { href: string; label: string }; app?: boolean;
}) {
  return <ConsoleHeader title={title} description={lede} actions={actions} back={back} />;
}

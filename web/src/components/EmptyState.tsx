import { ConsoleEmpty } from "./console";

/** Nothing to list on a console page. */
export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return <ConsoleEmpty title={title}>{children}</ConsoleEmpty>;
}

import { EmptyNet } from "./illustrations";
import { EmptyState as E } from "./ui/PageState";

/** The old EmptyState on the new one. */
export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return <E art={<EmptyNet />} title={title}>{children}</E>;
}

import { Notice, type Signal } from "./ui/Notice";

type Variant = "good" | "warn" | "bad" | "info";
const SIGNAL: Record<Variant, Signal> = { good: "done", warn: "yellow", bad: "red", info: "whistle" };

/** The old Flash, drawn as a referee-scale Notice. For screens not yet rebuilt. */
export function Flash({ variant = "info", title, children }: { variant?: Variant; title: string; children?: React.ReactNode; autoDismissMs?: number }) {
  return <Notice signal={SIGNAL[variant]} title={title} className="mb-4">{children}</Notice>;
}

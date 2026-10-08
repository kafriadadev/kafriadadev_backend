import { Metric } from "./console";

/** One figure on the console overview. */
export function Stat(props: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: "good" | "warn" | "bad"; href?: string;
}) {
  return <Metric {...props} />;
}

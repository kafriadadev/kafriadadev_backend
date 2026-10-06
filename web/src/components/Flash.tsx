type Variant = "good" | "warn" | "bad" | "info";

const PREFIX: Record<Variant, string> = { good: "Done", warn: "Check this", bad: "Problem", info: "" };

/** A status message after a form or a redirect. Stays until the page changes. */
export function Flash({
  variant = "info",
  title,
  children,
}: {
  variant?: Variant;
  title: string;
  children?: React.ReactNode;
  /** Accepted for compatibility; unused until the redesign's notices. */
  autoDismissMs?: number;
}) {
  return (
    <div role={variant === "bad" ? "alert" : "status"} data-variant={variant}>
      <p>
        <strong>{PREFIX[variant] ? `${PREFIX[variant]}: ` : ""}{title}</strong>
      </p>
      {children}
    </div>
  );
}

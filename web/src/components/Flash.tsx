"use client";

import { useEffect, useRef, useState } from "react";

type Variant = "good" | "warn" | "bad" | "info";

/**
 * A status message, styled like everything else printed on this document
 * (`.notice`, `--plate-*` tokens — see globals.css) rather than as a generic
 * web toast.
 *
 * Works identically with JavaScript off: the markup below is exactly what the
 * page already rendered as a plain `<div className="notice">`, so a client
 * without JS sees the same message, just without the entrance and the
 * auto-dismiss. Both of those are enhancements, never the only way to read it.
 */
const ICON: Record<Variant, string> = { good: "✓", warn: "!", bad: "✕", info: "" };

export function Flash({
  variant = "info",
  title,
  children,
  autoDismissMs,
}: {
  variant?: Variant;
  title: string;
  children?: React.ReactNode;
  /** Success messages only, normally — an error or warning stays until read. */
  autoDismissMs?: number;
}) {
  const [dismissed, setDismissed] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Screen readers land where the user's attention is needed; a success
    // notice does not steal focus from what they were already doing.
    if (variant === "bad" || variant === "warn") ref.current?.focus();
    if (!autoDismissMs) return;
    const timer = setTimeout(() => setDismissed(true), autoDismissMs);
    return () => clearTimeout(timer);
  }, [variant, autoDismissMs]);

  if (dismissed) return null;

  const className = variant === "info" ? "notice flash" : `notice notice--${variant} flash`;

  return (
    <div
      ref={ref}
      className={className}
      role={variant === "bad" ? "alert" : "status"}
      tabIndex={-1}
    >
      <p className="notice__title">
        {ICON[variant] ? (
          <span className="flash__icon" aria-hidden="true">{ICON[variant]}</span>
        ) : null}
        {title}
      </p>
      {children}
    </div>
  );
}

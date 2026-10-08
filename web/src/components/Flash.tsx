import { IconAlertTriangle, IconGoal, IconInfoCircle, IconRedCard } from "./icons";
import { cn } from "@/lib/cn";

type Variant = "good" | "warn" | "bad" | "info";

const STYLE: Record<Variant, { box: string; icon: React.ReactNode }> = {
  good: { box: "kc-alert-good", icon: <IconGoal size={20} className="text-check" aria-hidden="true" /> },
  warn: { box: "kc-alert-warn", icon: <IconAlertTriangle size={20} aria-hidden="true" /> },
  bad: { box: "kc-alert-bad", icon: <IconRedCard size={20} aria-hidden="true" /> },
  info: { box: "kc-alert-info", icon: <IconInfoCircle size={20} aria-hidden="true" /> },
};

/** A message at the top of a console page: what happened, in one line, and what it means. */
export function Flash({ variant = "info", title, children }: { variant?: Variant; title: string; children?: React.ReactNode; autoDismissMs?: number }) {
  const s = STYLE[variant];
  return (
    <div role={variant === "bad" || variant === "warn" ? "alert" : "status"} className={cn("kc-alert-box kc-round mb-4 flex gap-3 px-4 py-3 text-sm", s.box)}>
      <span className="mt-px shrink-0">{s.icon}</span>
      <div className="min-w-0 space-y-1">
        <p className="font-bold">{title}</p>
        {children ? <div className="kc-alert space-y-1">{children}</div> : null}
      </div>
    </div>
  );
}

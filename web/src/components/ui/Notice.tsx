import { IconCheck, IconFlag, IconRedCard, IconVarScreen, IconWhistle, IconYellowCard } from "@/components/icons";
import { cn } from "@/lib/cn";
import { RefChip } from "./RefChip";

/**
 * The referee scale. Every state is refereed: the football carries the
 * feeling, the words stay plain and kind.
 *
 * whistle  information, nothing wrong
 * yellow   something to fix; you can carry on
 * red      blocked or failed
 * var      being checked; wait
 * flag     not allowed here
 * done     done
 */
export type Signal = "whistle" | "yellow" | "red" | "var" | "flag" | "done";

const STYLE: Record<Signal, { box: string; icon: React.ReactNode }> = {
  whistle: { box: "bg-surface text-text border-line", icon: <IconWhistle aria-hidden="true" /> },
  yellow: { box: "bg-warn-bg text-on-warn border-[var(--boot)]", icon: <IconYellowCard className="motion-flick" aria-hidden="true" /> },
  red: { box: "bg-danger-bg text-text border-danger", icon: <IconRedCard className="motion-flick" aria-hidden="true" /> },
  var: { box: "bg-check-bg text-text border-check", icon: <IconVarScreen className="text-check" aria-hidden="true" /> },
  flag: { box: "bg-surface text-text border-text", icon: <IconFlag aria-hidden="true" /> },
  done: { box: "bg-check-bg text-text border-check", icon: <IconCheck className="text-check" aria-hidden="true" /> },
};

/**
 * What happened (title), what is still safe and what to do (children), one
 * action, and a reference code to read down the phone. Red and yellow are
 * announced as alerts; the rest as status.
 */
export function Notice({
  signal = "whistle",
  title,
  children,
  action,
  reference,
  referenceHelp,
  className,
}: {
  signal?: Signal;
  title: React.ReactNode;
  children?: React.ReactNode;
  action?: React.ReactNode;
  reference?: string;
  referenceHelp?: string;
  className?: string;
}) {
  const s = STYLE[signal];
  const urgent = signal === "red" || signal === "yellow";
  return (
    <div
      role={urgent ? "alert" : "status"}
      className={cn("flex gap-3 rounded-card border-2 border-l-[6px] p-4", s.box, className)}
    >
      <span className="mt-0.5 shrink-0">{s.icon}</span>
      <div className="min-w-0 flex-1 space-y-2">
        <p className={cn("font-bold", signal === "red" && "text-danger")}>{title}</p>
        {children ? <div className="space-y-2">{children}</div> : null}
        {action ? <div className="pt-1">{action}</div> : null}
        {reference ? <RefChip code={reference} help={referenceHelp} /> : null}
      </div>
    </div>
  );
}

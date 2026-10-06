import { IconShieldCheck, IconUser } from "@/components/icons";
import { cn } from "@/lib/cn";

export type Tone = "neutral" | "good" | "warn" | "bad" | "check";

const TONE: Record<Tone, string> = {
  neutral: "bg-surface-2 text-text",
  good: "bg-pitch text-on-pitch",
  warn: "bg-warn-bg text-on-warn",
  bad: "bg-danger-bg text-danger",
  check: "bg-check-bg text-check",
};

/** A short status: always a word, an icon when it helps. */
export function Pill({ tone = "neutral", icon, children, className }: { tone?: Tone; icon?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex min-h-7 items-center gap-1.5 rounded-pill px-3 text-xs font-bold", TONE[tone], className)}>
      {icon}
      {children}
    </span>
  );
}

/**
 * Verified or not. Unverified is neutral, never a warning: every athlete has
 * an ID and can play either way.
 */
export function VerifiedBadge({ verified, labels }: { verified: boolean; labels: { verified: string; unverified: string } }) {
  return verified ? (
    <Pill tone="good" icon={<IconShieldCheck size={16} aria-hidden="true" />}>{labels.verified}</Pill>
  ) : (
    <Pill tone="neutral" icon={<IconUser size={16} aria-hidden="true" />}>{labels.unverified}</Pill>
  );
}

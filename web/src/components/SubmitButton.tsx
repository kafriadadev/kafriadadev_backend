import { SubmitButton as S } from "./ui/SubmitButton";

/** The old SubmitButton on the new one. */
export function SubmitButton({ children, pending = "Working…", disabled, name, value, variant = "primary" }: {
  children: React.ReactNode; className?: string; pending?: string; detail?: string; disabled?: boolean; name?: string; value?: string;
  /** "danger" for anything that takes something away: withdraw, revoke, suspend, reject. */
  variant?: "primary" | "secondary" | "danger";
}) {
  return <S pendingLabel={pending} disabled={disabled} name={name} value={value} variant={variant} size="md" block={false}>{children}</S>;
}

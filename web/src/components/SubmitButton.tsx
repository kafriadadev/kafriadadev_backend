import { SubmitButton as S } from "./ui/SubmitButton";

/** The console's submit button: compact, and still says what is happening while it works. */
export function SubmitButton({ children, pending = "Working…", disabled, name, value, variant = "primary" }: {
  children: React.ReactNode; className?: string; pending?: string; detail?: string; disabled?: boolean; name?: string; value?: string;
  /**
   * "danger" for the button that confirms taking something away (withdraw, revoke, reject);
   * "quietDanger" for the same action offered beside others in a list.
   */
  variant?: "primary" | "secondary" | "danger" | "quietDanger";
}) {
  return <S pendingLabel={pending} disabled={disabled} name={name} value={value} variant={variant} size="sm" block={false}>{children}</S>;
}

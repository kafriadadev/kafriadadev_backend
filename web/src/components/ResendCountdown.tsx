/**
 * The resend form. The server enforces the wait and says so; the live
 * countdown returns with the redesign.
 */
export function ResendCountdown({
  children,
}: {
  seconds: number;
  children: React.ReactNode;
}) {
  return <>{children}</>;
}

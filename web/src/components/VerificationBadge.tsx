/** Whether an athlete's identity has been checked by their coordinator. */
export function VerificationBadge({ verified }: { verified: boolean }) {
  return <strong>{verified ? "Verified" : "Unverified"}</strong>;
}

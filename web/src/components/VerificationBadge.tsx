/**
 * Whether an athlete's identity has been checked by their coordinator.
 *
 * Every athlete has an ID and can play for a club either way. Verified means a
 * photograph and an identity document were checked against the record.
 */
export function VerificationBadge({ verified }: { verified: boolean }) {
  return verified ? (
    <span className="pill pill--issued">Verified</span>
  ) : (
    <span className="pill pill--pending">Unverified</span>
  );
}

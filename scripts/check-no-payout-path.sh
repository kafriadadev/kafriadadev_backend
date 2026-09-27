#!/usr/bin/env bash
# =============================================================================
# Refuse to build if a money-out path has appeared anywhere in the source.
#
# The wallet is a record book. Money enters through Paystack and has no way out.
# That is not a product preference — if users could withdraw funds or send them
# to each other, the Central Bank of Nigeria would treat KAFRIADA as a deposit
# taker, and that licensing fight would end the pilot.
#
# A comment in an architecture document does not survive staff turnover, a
# late-night feature request, or a well-meaning contributor who thinks a wallet
# "obviously" needs a withdraw button. This check does.
#
# Refunds are legitimate and deliberately absent from the forbidden list: they
# are made by a human inside Paystack's own dashboard and only *recorded* here,
# by wallet.record_reversal(). No endpoint in this system moves money.
#
# ALLOWLIST: some of these words have a second, unrelated meaning in this
# codebase — "withdraw a verification badge" (ADM-03) is revoking a status,
# not moving money. Rather than weaken FORBIDDEN itself, specific lines that
# have been checked by hand and confirmed to be about something other than a
# payout are listed below by their exact "path:line:content" text, as this
# script itself prints it (the line number is ignored). A line whose wording changes, stops
# matching and fails the build again — on purpose, so an edit near an
# allowlisted line always gets a fresh look rather than riding on an old
# approval.
#
# To add one: run this script, confirm the new match is not a payout path
# (same standard as any other line here — it must be about something other
# than money leaving the wallet), then paste its exact printed line below.
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

FORBIDDEN='withdraw|payout|pay_out|cash_out|cashout|send_money|transfer_funds|p2p_transfer|remit'

ALLOWLIST_FILE="$(mktemp)"
trap 'rm -f "$ALLOWLIST_FILE"' EXIT
cat > "$ALLOWLIST_FILE" <<'EOF'
api/src/kafriada/api/v1/athletes.py:91:    # An approved badge that was later withdrawn. Shown so nobody trusts a stale card.
api/src/kafriada/api/v1/athletes.py:92:    verification_withdrawn: bool = False
api/src/kafriada/api/v1/athletes.py:285:        verification_withdrawn=profile.verification_withdrawn,
api/src/kafriada/api/v1/verification.py:1:"""Verification: the athlete's uploads and status, the reviewer's queue, a withdrawal,
api/src/kafriada/api/v1/verification.py:11:* **A super administrator** (``verification.revoke``) withdraws a badge, with a reason
api/src/kafriada/api/v1/verification.py:341:    summary="Find an athlete's verification request, to withdraw it (ADM-03)",
api/src/kafriada/api/v1/verification.py:385:        # Not verified, withdrawn, or no such athlete: all the same answer.
api/src/kafriada/api/v1/verification.py:390:        # Short, so a withdrawal takes effect within a minute rather than a day.
api/src/kafriada/contexts/access/service.py:1154:    Public so other contexts (withdrawing a verification) use the same check, with
api/src/kafriada/contexts/identity/service.py:401:    verification_withdrawn: bool = False
api/src/kafriada/contexts/identity/service.py:453:        verification_withdrawn=row["was_revoked"] and not row["is_verified"],
api/src/kafriada/contexts/ledger/reversal.py:3:**KAFRIADA cannot send money, and this does not change that.** There is no payout path
api/src/kafriada/contexts/ledger/reversal.py:20:A reversal does not withdraw the athlete's verification. Taking back a badge is its own
api/src/kafriada/contexts/verification/service.py:14:* A withdrawal (``revoked``) needs a reason and the actor's password again.
api/src/kafriada/contexts/verification/service.py:57:SMS_REVOKED = "KAFRIADA: your verification has been withdrawn. Contact your LGA coordinator for help."
api/src/kafriada/contexts/verification/service.py:65:    "revoked": "Your KAFRIADA verification has been withdrawn",
api/src/kafriada/contexts/verification/service.py:93:    reason: str | None  # the reviewer's words on the latest rejection or withdrawal
api/src/kafriada/contexts/verification/service.py:612:        raise Refused("Say why this is being withdrawn. It is kept permanently.", code="reason")
api/src/kafriada/migrations/versions/0007_media_and_verification.py:14:    draft ──paid──▶ under_review ──approve──▶ approved ──withdraw──▶ revoked
api/src/kafriada/migrations/versions/0007_media_and_verification.py:137:    # At most one live request per athlete; only a withdrawal frees the slot.
api/src/kafriada/migrations/versions/0007_media_and_verification.py:168:            -- Mandatory for a rejection and a withdrawal, and shown to the
web/src/app/a/[kuid]/page.tsx:141:                ) : profile.verification_withdrawn ? (
web/src/app/a/[kuid]/page.tsx:142:                  "Verification withdrawn"
web/src/app/admin/reversal/page.tsx:34: * no payout path and nothing here calls Paystack. Same two-step shape as
web/src/app/admin/revoke/actions.ts:29:  if (!reason) bounceBack("Say why this is being withdrawn.");
web/src/app/admin/revoke/page.tsx:27:  revoked: "Already withdrawn",
web/src/app/admin/revoke/page.tsx:55:          <p style={{ marginBottom: 0 }}>Only a super administrator can withdraw a badge.</p>
web/src/app/admin/revoke/page.tsx:87:        withdrawn with a reason. The badge and photo come down immediately;
web/src/app/admin/revoke/page.tsx:94:            The badge for <span className="kuid">{done}</span> has been withdrawn.
web/src/app/admin/revoke/page.tsx:167:                Nothing to withdraw — only an approved verification can be.
web/src/app/photo/[kuid]/route.ts:10: * approved — so a withdrawn badge stops showing its photo within a minute, and a
web/src/app/photo/[kuid]/route.ts:20:      // Short, so a withdrawal is not held up by a cache.
web/src/app/verify/page.tsx:95:        <Start v={v} withdrawn={v.state === "revoked"} />
web/src/app/verify/page.tsx:142:function Start({ v, withdrawn }: { v: Verification; withdrawn: boolean }) {
web/src/app/verify/page.tsx:147:      {withdrawn ? (
web/src/app/verify/page.tsx:149:          <p className="notice__title">Your earlier verification was withdrawn</p>
web/src/lib/api.ts:40:  verification_withdrawn: boolean;
web/src/lib/api.ts:415:/** ADM-03: find an athlete's verification request by KUID, to withdraw it. */
api/src/kafriada/api/v1/clubs.py:205:    summary="Remove a player from the roster, or withdraw an invitation",
api/src/kafriada/contexts/clubs/service.py:445:    """End a membership, or withdraw an invitation. Bounded to this club's own teams."""
api/src/kafriada/contexts/clubs/verification.py:461:        raise Refused("Say why this is being withdrawn. It is kept permanently.", code="reason", field="reason")
api/src/kafriada/contexts/clubs/verification.py:510:            sms=f"KAFRIADA: {row['name']}'s verified badge has been withdrawn. Sign in to see why.",
api/src/kafriada/contexts/clubs/verification.py:511:            subject=f"{row['name']}'s verified badge has been withdrawn",
api/src/kafriada/contexts/clubs/verification.py:512:            email=f"{row['name']}'s verified badge has been withdrawn on KAFRIADA.\n\nReason: {reason}",
web/src/app/admin/clubs/page.tsx:72:          title={done === "approved" ? "Club approved" : done === "revoked" ? "Verification withdrawn" : "Club suspended"}
web/src/app/admin/clubs/[id]/revoke/actions.ts:24:  if (!reason) redirect(`${back}?${new URLSearchParams({ error: "Say why this is being withdrawn." })}`);
web/src/app/admin/clubs/[id]/revoke/page.tsx:108:              Nothing to withdraw — only a currently verified club can be.
EOF

SEARCH_PATHS=(api/src web/src web/app)
EXISTING=()
for p in "${SEARCH_PATHS[@]}"; do
  [ -d "$p" ] && EXISTING+=("$p")
done

if [ ${#EXISTING[@]} -eq 0 ]; then
  echo "check-no-payout-path: no source directories yet, nothing to check"
  exit 0
fi

# --exclude-dir keeps generated and vendored code out of it. The check is on
# code we write, not on a dependency that happens to contain the word.
raw_matches=$(grep -rInE "$FORBIDDEN" "${EXISTING[@]}" \
      --exclude-dir=node_modules \
      --exclude-dir=__pycache__ \
      --exclude-dir=.next \
      --exclude-dir=.venv \
      --exclude="*.lock" \
      2>/dev/null || true)

if [ -z "$raw_matches" ]; then
  echo "check-no-payout-path: clean"
  exit 0
fi

# Compared as "path:content" with the line number dropped, so an edit elsewhere in
# a file (which shifts every line below it) does not break the allowlist, while a
# change to an allowlisted line's own wording still does.
matches=$(awk -v allow="$ALLOWLIST_FILE" '
  function key(line,   path, rest) {
    path = substr(line, 1, index(line, ":") - 1)
    rest = line
    sub(/^[^:]*:[0-9]+:/, "", rest)
    return path ":" rest
  }
  BEGIN { while ((getline l < allow) > 0) ok[key(l)] = 1 }
  !(key($0) in ok)
' <<<"$raw_matches")

if [ -n "$matches" ]; then
  echo ""
  echo "  BUILD REFUSED — a money-out path appeared in the source."
  echo ""
  echo "$matches" | sed 's/^/    /'
  echo ""
  echo "  The wallet records money arriving and has no mechanism for money"
  echo "  leaving. No withdrawal, payout or peer-to-peer endpoint may exist —"
  echo "  not disabled, not behind a flag, absent."
  echo ""
  echo "  If you are recording a refund that a human already made in the"
  echo "  Paystack dashboard, use wallet.record_reversal(): it writes a ledger"
  echo "  line and moves no money."
  echo ""
  echo "  If this line really is unrelated to money leaving the wallet (like"
  echo "  the verification-badge 'withdraw' language already allowlisted"
  echo "  above), add its exact text to ALLOWLIST_FILE in this script."
  echo ""
  exit 1
fi

allowed_count=$(printf '%s\n' "$raw_matches" | wc -l)
echo "check-no-payout-path: clean ($allowed_count allowlisted, none forbidden)"

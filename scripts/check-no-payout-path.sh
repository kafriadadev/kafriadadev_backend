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
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

FORBIDDEN='withdraw|payout|pay_out|cash_out|cashout|send_money|transfer_funds|p2p_transfer|remit'

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
if matches=$(grep -rInE "$FORBIDDEN" "${EXISTING[@]}" \
      --exclude-dir=node_modules \
      --exclude-dir=__pycache__ \
      --exclude-dir=.next \
      --exclude-dir=.venv \
      --exclude="*.lock" \
      2>/dev/null); then
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
  exit 1
fi

echo "check-no-payout-path: clean"

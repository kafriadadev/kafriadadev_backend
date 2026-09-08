#!/usr/bin/env bash
# Installs the pre-commit hook. Run once after cloning.
#
# The hook catches an honest mistake at the moment it happens; CI catches the
# machine that never installed the hook. Both are needed — a secret that reaches
# a remote is compromised whether or not a later commit removes it, because it
# stays in the git objects and in every clone.
set -euo pipefail

cd "$(dirname "$0")/.."
HOOK=".git/hooks/pre-commit"

cat > "$HOOK" <<'HOOK_BODY'
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

fail() { echo ""; echo "  COMMIT REFUSED — $1"; echo ""; exit 1; }

# --- 1. Never commit an environment file --------------------------------
if git diff --cached --name-only | grep -qE '(^|/)\.env($|\.)' ; then
  if ! git diff --cached --name-only | grep -qE '\.env\.example$'; then
    fail "an .env file is staged. Secrets belong in the host's secret store."
  fi
fi

# --- 2. Never commit a private key --------------------------------------
if git diff --cached --name-only | grep -qE '\.(pem|key|p12|pfx|jks|keystore)$'; then
  fail "a key file is staged."
fi

# --- 3. Scan the staged diff for secrets ---------------------------------
if command -v gitleaks >/dev/null 2>&1; then
  gitleaks protect --staged --redact --no-banner \
    || fail "gitleaks found a secret in the staged changes."
else
  echo "  note: gitleaks not installed — CI will still scan. Install it for local cover."
fi

# --- 4. No money-out path ------------------------------------------------
bash scripts/check-no-payout-path.sh >/dev/null \
  || fail "a withdrawal or payout path appeared. See scripts/check-no-payout-path.sh"

# --- 5. Lint and type-check whatever Python is staged --------------------
staged_py=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true)
if [ -n "$staged_py" ] && [ -x api/.venv/Scripts/ruff.exe ]; then
  api/.venv/Scripts/ruff.exe check $staged_py || fail "ruff found problems."
elif [ -n "$staged_py" ] && command -v ruff >/dev/null 2>&1; then
  ruff check $staged_py || fail "ruff found problems."
fi

exit 0
HOOK_BODY

chmod +x "$HOOK"
echo "installed $HOOK"
echo ""
echo "For full local cover, install gitleaks:"
echo "  winget install gitleaks       (Windows)"
echo "  brew install gitleaks         (macOS)"

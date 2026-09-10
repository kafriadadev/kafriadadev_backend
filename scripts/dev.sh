#!/usr/bin/env bash
# =============================================================================
# Start both tiers for local development or a demonstration.
#
#   bash scripts/dev.sh
#
#   API   http://127.0.0.1:8010   the domain tier — every rule, the only
#                                 database credentials
#   Web   http://localhost:3000   the presentation tier — the browser talks
#                                 only to this
#
# Stop both with Ctrl-C.
#
# The API binds to 127.0.0.1 rather than 0.0.0.0 deliberately. It is not meant
# to be reachable from anywhere except the presentation tier, and a laptop that
# joins conference and hotel networks should not be serving it to the room.
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

if [ ! -f api/.env ]; then
  echo "api/.env is missing. Copy .env.example and fill it in." >&2
  exit 1
fi

# Load configuration for the API process. Values stay in this shell; nothing is
# echoed, because these are database credentials and signing keys.
set -a
# shellcheck disable=SC1091
. api/.env
set +a

cleanup() {
  echo ""
  echo "stopping..."
  # Kill the whole process group so uvicorn's reloader children go too.
  [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true
  [ -n "${WEB_PID:-}" ] && kill "$WEB_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> starting the API on 127.0.0.1:8010"
( cd "$ROOT/api" && ./.venv/Scripts/python.exe -m uvicorn kafriada.main:app \
    --host 127.0.0.1 --port 8010 --reload ) &
API_PID=$!

# Wait for it to answer before starting the web tier, so the first page load
# does not fail while the API is still importing.
echo "    waiting for the API to answer..."
for _ in $(seq 1 60); do
  if curl -fsS --max-time 2 http://127.0.0.1:8010/healthz >/dev/null 2>&1; then
    echo "    API is up"
    break
  fi
  sleep 1
done

echo "==> starting the web tier on localhost:3000"
( cd "$ROOT/web" && npm run dev ) &
WEB_PID=$!

cat <<'BANNER'

  ---------------------------------------------------------------
   KAFRIADA CORE is running

     Register     http://localhost:3000/register
     Look up      http://localhost:3000/find
     A profile    http://localhost:3000/a/KA-NG-JG-BKD-2026-000115

   Ctrl-C stops both.
  ---------------------------------------------------------------

BANNER

wait

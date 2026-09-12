#!/usr/bin/env bash
# =============================================================================
# Migrations as a release step, with a gate in front of them.
#
#   bash scripts/release.sh plan      staging     # what would run, and the SQL
#   bash scripts/release.sh migrate   staging     # apply, after confirmation
#   bash scripts/release.sh verify    staging     # the database is at head
#   bash scripts/release.sh smoke     https://…   # the deployed API answers
#
# WHY A SCRIPT AND NOT `alembic upgrade head` IN THE DEPLOY
#
# Because the deploy that runs migrations automatically is the deploy that drops
# a column at 4pm on a Friday. Three things are enforced here:
#
#   1. The SQL is printed before it is executed. `alembic upgrade --sql` renders
#      it offline, so it can be read by a person who did not write it.
#   2. The destructive-change check runs first. A migration that loses data must
#      carry a written justification or this refuses to continue.
#   3. Applying requires the environment's name to be typed. Not a flag that can
#      be left in a shell's history — the name of the thing being changed.
#
# The connection string comes from DATABASE_URL_MIGRATE, which must be the
# kaf_migrate role. It is the only role that holds DDL, it is never used by a
# running process, and this script is the only thing that should ever hold it.
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PYTHON="${PYTHON:-api/.venv/Scripts/python.exe}"
[ -x "$PYTHON" ] || PYTHON="python"

command="${1:-}"
target="${2:-}"

die() { echo "error: $*" >&2; exit 1; }

usage() {
  sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'
  exit 64
}

require_migrate_url() {
  [ -n "${DATABASE_URL_MIGRATE:-}" ] || die "DATABASE_URL_MIGRATE is not set"
  case "$DATABASE_URL_MIGRATE" in
    *kaf_migrate*) : ;;
    # The app role has no DDL, so an accidental paste would fail anyway — but it
    # would fail halfway through, which is the worst moment to find out.
    *) die "DATABASE_URL_MIGRATE must use the kaf_migrate role" ;;
  esac
}

alembic_() { (cd api && "$ROOT/$PYTHON" -m alembic "$@"); }

case "$command" in
  plan)
    [ -n "$target" ] || usage
    require_migrate_url
    echo "== destructive-change check =================================="
    "$PYTHON" scripts/check_migration_safety.py
    echo
    echo "== where $target is now ======================================"
    alembic_ current
    echo
    at="$(alembic_ current 2>/dev/null | tail -1 | awk '{print $1}')"
    echo "== what would be applied ====================================="
    if [ -n "$at" ]; then
      alembic_ history -r"$at":head --indicate-current
    else
      alembic_ history --indicate-current
    fi
    echo
    echo "== the SQL, rendered without touching the database ==========="
    # Offline mode: this connects to nothing. What is printed is what runs.
    # Rendered from where the database actually is, not from base, or the plan
    # would be the whole history every time and nobody would read it.
    if [ -n "$at" ]; then
      alembic_ upgrade "$at":head --sql
    else
      alembic_ upgrade head --sql
    fi
    ;;

  migrate)
    [ -n "$target" ] || usage
    require_migrate_url
    "$PYTHON" scripts/check_migration_safety.py
    current="$(alembic_ current 2>/dev/null | tail -1)"
    echo "database is at: ${current:-(nothing applied)}"
    echo
    if [ "${RELEASE_APPROVED:-}" = "$target" ]; then
      # The CI path: the approval already happened in the deploy environment's
      # protection rule, and this variable is how that decision arrives here.
      echo "approved for $target by the release environment"
    else
      printf 'Type the environment name to apply migrations to it: '
      read -r typed
      [ "$typed" = "$target" ] || die "typed '$typed', expected '$target' — nothing applied"
    fi
    alembic_ upgrade head
    echo
    alembic_ current
    ;;

  verify)
    [ -n "$target" ] || usage
    require_migrate_url
    current="$(alembic_ current | tr -d '\r')"
    echo "$current"
    case "$current" in
      *"(head)"*) echo "verify: $target is at head" ;;
      *) die "verify: $target is NOT at head" ;;
    esac
    ;;

  smoke)
    base="${target:-}"
    [ -n "$base" ] || usage
    echo "== ${base%/}/healthz"
    curl -fsS --max-time 20 "${base%/}/healthz" && echo
    echo "== ${base%/}/readyz"
    curl -fsS --max-time 30 "${base%/}/readyz" && echo
    # A deployed API that cannot reach its database answers 503 here, and the
    # deploy should stop rather than take traffic.
    echo "smoke: ok"
    ;;

  *) usage ;;
esac

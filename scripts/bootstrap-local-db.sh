#!/usr/bin/env bash
# =============================================================================
# One-time local database setup.
#
#   docker compose -f infra/docker-compose.yml up -d
#   bash scripts/bootstrap-local-db.sh
#
# Creates the four roles, applies the privilege boundary, and runs migrations.
# The passwords below are for a container that listens only on 127.0.0.1 and
# holds no real data. Never reuse this pattern anywhere else — staging and
# production credentials come from the host's secret store.
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

: "${LOCAL_DB_PASSWORD:=local_dev_only}"
ADMIN_URL="${ADMIN_URL:-postgresql://kafriada_admin:local_dev_only_not_a_real_secret@localhost:5432/kafriada}"

echo "==> creating roles and locking down the database"
psql "$ADMIN_URL" -v ON_ERROR_STOP=1 \
  -v app_password="$LOCAL_DB_PASSWORD" \
  -v money_password="$LOCAL_DB_PASSWORD" \
  -v reader_password="$LOCAL_DB_PASSWORD" \
  -v migrate_password="$LOCAL_DB_PASSWORD" \
  -f infra/bootstrap-roles.sql

echo "==> running migrations as kaf_migrate"
export DATABASE_URL_MIGRATE="postgresql+psycopg://kaf_migrate:${LOCAL_DB_PASSWORD}@localhost:5432/kafriada"
(cd api && alembic upgrade head)

cat <<EOF

Done. Add these to your api/.env if they are not there already:

  DATABASE_URL_MIGRATE=postgresql+psycopg://kaf_migrate:${LOCAL_DB_PASSWORD}@localhost:5432/kafriada
  DATABASE_URL_APP=postgresql+psycopg://kaf_app:${LOCAL_DB_PASSWORD}@localhost:5432/kafriada
  DATABASE_URL_MONEY=postgresql+psycopg://kaf_money:${LOCAL_DB_PASSWORD}@localhost:5432/kafriada
  DATABASE_URL_READER=postgresql+psycopg://kaf_reader:${LOCAL_DB_PASSWORD}@localhost:5432/kafriada

Then prove the guarantees hold on your machine:

  cd api && pytest -m db -v

EOF

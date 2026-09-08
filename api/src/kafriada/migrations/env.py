"""Alembic environment.

Migrations connect as ``kaf_migrate``, which is the only role holding DDL. That
connection string is separate from the application's on purpose: a running
process must never be able to alter schema or disable the audit log's triggers.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate is intentionally unavailable. Every table in this system is
# written as explicit, reviewed SQL — the privilege grants, partial indexes,
# check constraints and immutability triggers that carry the security properties
# are exactly the things autogenerate silently drops.
target_metadata = None


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL_MIGRATE")
    if not url:
        raise RuntimeError(
            "DATABASE_URL_MIGRATE is not set. Migrations run as kaf_migrate, not "
            "as the application role. See infra/bootstrap-roles.sql."
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Alembic creates its version table before the first migration runs, so
        # the schema it lives in has to exist first. This is the one piece of DDL
        # that cannot itself be a migration.
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS ops AUTHORIZATION kaf_migrate"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            # Alembic's own bookkeeping table lives in ops alongside everything
            # else operational, not in public — which this system revokes.
            version_table="alembic_version",
            version_table_schema="ops",
        )
        # One transaction for the whole migration run. PostgreSQL has
        # transactional DDL, so a failure half way through leaves the schema
        # exactly as it was rather than half-migrated.
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

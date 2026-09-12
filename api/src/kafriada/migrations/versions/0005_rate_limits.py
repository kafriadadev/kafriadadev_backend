"""Counters for per-address rate limiting.

Revision ID: 0005_rate_limits
Revises: 0004_outbox_and_codes
Create Date: 2026-09-12

**What this closes.** Two limits already exist and both are per person: an
account locks after repeated wrong passwords, and a phone number may be sent
five codes a day. Neither counts what one *source* is doing. So a single caller
could try one password against ten thousand accounts — never tripping any
account's lock — or ask for codes to ten thousand different numbers, which is
somebody else's phone ringing at 3am and our SMS bill.

**Why a table and not Redis.** Redis is the usual answer and is genuinely better
at this: counters live in memory, expire themselves, and are shared by every
server. It is also another service to run, secure, pay for and monitor. These
limits apply to four endpoints, not to every request, and pilot traffic is a few
thousand attempts a day — well inside what one Postgres table absorbs without
noticing. The counting sits behind ``ratelimit.hit()`` so the storage can be
swapped later without touching a single route.

**Fixed windows, not sliding.** A sliding window needs every individual event
kept; a fixed window needs one row per bucket per period. The cost is that a
caller can spend a full allowance at the end of one window and again at the
start of the next. For "stop the bulk attack and the runaway bill" that is
irrelevant, and it is a great deal cheaper.

**No personal data.** The key is hashed with the server pepper before it is
stored, so this table holds no IP addresses. It is operational counting, not a
record of who did what — the audit log is where that belongs, and it already
stores the address for the events that matter.
"""

from __future__ import annotations

from alembic import op

revision = "0005_rate_limits"
down_revision = "0004_outbox_and_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ops.rate_counters (
            -- HMAC of "<bucket>:<subject>" under the server pepper. Opaque on
            -- purpose: a leaked copy of this table reveals no addresses.
            key_hash     text        NOT NULL,

            -- Start of the fixed window this row counts, so (key, window) is
            -- naturally unique and the UPSERT needs no read first.
            window_start timestamptz NOT NULL,
            window_secs  integer     NOT NULL,

            hits         integer     NOT NULL DEFAULT 0,

            PRIMARY KEY (key_hash, window_start, window_secs)
        )
        """
    )

    # Pruning is "everything older than now" — an index on the window alone is
    # what that scan wants.
    op.execute(
        "CREATE INDEX rate_counters_window_idx ON ops.rate_counters (window_start)"
    )

    # The app role counts and prunes its own counters. Deliberately no money
    # role: nothing about a payment is throttled here.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ops.rate_counters TO kaf_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ops.rate_counters")

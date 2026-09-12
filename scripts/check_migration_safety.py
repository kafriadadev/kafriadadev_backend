#!/usr/bin/env python
"""Refuse a migration that destroys data without someone saying so out loud.

    python scripts/check_migration_safety.py

A release step that applies migrations automatically is only safe if a migration
cannot quietly drop a column. This reads every migration's ``upgrade()`` and
fails on statements that lose data, unless the file carries an approval marker:

    DESTRUCTIVE_MIGRATION_APPROVED = "why this is safe, and who agreed"

``downgrade()`` is exempt. A downgrade is expected to destroy what its upgrade
built; that is the point of one, and it only runs when a human asks it to.

This is a text check, not a parser, and that is a deliberate trade: it errs
towards complaining. A false alarm costs one line of justification in the
migration. A missed ``DROP COLUMN`` costs a column of a national register.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

VERSIONS = Path(__file__).resolve().parent.parent / "api/src/kafriada/migrations/versions"

MARKER = "DESTRUCTIVE_MIGRATION_APPROVED"

# Each pattern is something that cannot be undone by running the next migration.
DESTRUCTIVE = (
    (re.compile(r"\bDROP\s+TABLE\b", re.I), "DROP TABLE"),
    (re.compile(r"\bDROP\s+COLUMN\b", re.I), "DROP COLUMN"),
    (re.compile(r"\bDROP\s+SCHEMA\b", re.I), "DROP SCHEMA"),
    (re.compile(r"\bTRUNCATE\b", re.I), "TRUNCATE"),
    (re.compile(r"\bDELETE\s+FROM\b", re.I), "DELETE FROM"),
    (re.compile(r"\bALTER\s+COLUMN\b[^\n]*\bTYPE\b", re.I), "ALTER COLUMN ... TYPE"),
    (re.compile(r"\bDROP\s+(?:TRIGGER|FUNCTION)\b", re.I), "DROP TRIGGER/FUNCTION"),
    # Revoking a grant is not data loss, but revoking the audit log's protection
    # is the one change that must never pass unnoticed.
    (re.compile(r"\bALTER\s+TABLE\b[^\n]*\bDISABLE\s+TRIGGER\b", re.I), "DISABLE TRIGGER"),
)


def upgrade_body(source: str) -> str:
    """The text of upgrade(), up to the next top-level def."""
    start = source.find("def upgrade(")
    if start < 0:
        return ""
    rest = source[start:]
    end = rest.find("\ndef ", 1)
    return rest if end < 0 else rest[:end]


def main() -> int:
    if not VERSIONS.is_dir():
        print(f"no migrations directory at {VERSIONS}")
        return 1

    problems: list[str] = []
    checked = 0
    for path in sorted(VERSIONS.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        checked += 1
        if MARKER in source:
            continue
        body = upgrade_body(source)
        for pattern, label in DESTRUCTIVE:
            if pattern.search(body):
                problems.append(f"{path.name}: upgrade() contains {label}")

    if problems:
        print("check-migration-safety: FAILED")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nIf the change is intended, state why in the migration:\n"
            f'    {MARKER} = "the column held nothing; agreed with X on DATE"\n'
            "and have it reviewed as a data-loss change, not as a schema tweak."
        )
        return 1

    print(f"check-migration-safety: clean ({checked} migrations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

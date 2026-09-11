"""Fixtures for the access tests: people with known passwords and roles.

Rows are created through the app role and left behind, like every other DB test
here — the app role cannot delete users or role grants, by design.
"""

from __future__ import annotations

import itertools
import time
from uuid import UUID

from sqlalchemy import text

from kafriada.db.engine import transaction
from kafriada.security.passwords import get_password_service

# Nigerian mobile shape inside the range the burst test uses, which no real
# subscriber holds. Serials from 5000 stay clear of the other tests' numbers.
_MARKER = f"{int(time.time()) % 100000:05d}"
_SERIALS = itertools.count(5000)

Grant = tuple[str, str, str | None]  # (role, scope_kind, scope_id)


def new_phone() -> str:
    return f"+2349{_MARKER}{next(_SERIALS):04d}"


def make_user(
    name: str,
    *,
    password: str | None = None,
    grants: list[Grant] | tuple[Grant, ...] = (),
) -> tuple[UUID, str]:
    """Create a user with the given grants. Returns (user_id, phone)."""
    phone = new_phone()
    password_hash = get_password_service().hash(password) if password else None
    with transaction() as session:
        user_id: UUID = session.execute(
            text(
                """
                INSERT INTO ops.users (full_name, phone_e164, password_hash)
                VALUES (:name, :phone, :hash)
                RETURNING id
                """
            ),
            {"name": f"{name} {_MARKER}", "phone": phone, "hash": password_hash},
        ).scalar_one()
        for role, kind, scope_id in grants:
            session.execute(
                text(
                    """
                    INSERT INTO ops.user_roles (user_id, role_code, scope_kind, scope_id, reason)
                    VALUES (:user_id, :role, :kind, :scope_id, 'test fixture')
                    """
                ),
                {"user_id": user_id, "role": role, "kind": kind, "scope_id": scope_id},
            )
    return user_id, phone


def sql(statement: str, **params: object) -> list[dict[str, object]]:
    """Run one statement as the app role and return its rows."""
    with transaction() as session:
        result = session.execute(text(statement), params)
        return [dict(r) for r in result.mappings().all()] if result.returns_rows else []


def audit_actions(subject_id: UUID | str) -> list[str]:
    rows = sql(
        "SELECT action FROM ops.audit_log WHERE subject_id = :s ORDER BY id",
        s=str(subject_id),
    )
    return [str(r["action"]) for r in rows]


def bearer(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}

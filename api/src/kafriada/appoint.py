"""Appoint the first super administrator.

    python -m kafriada.appoint --phone 08031234567 --reason "founding administrator"

Every later grant goes through the console, and asks a signed-in super administrator for
their password. The very first has nobody to ask, so it is a command run by someone who
already holds the database credentials — which is the only authority that exists before
the first administrator does. It is deliberately narrow: it only ever grants
``super_admin`` to a person who has already registered, it refuses to do it twice, and
it writes an audit row naming the operator's stated reason, so the appointment is on the
record like every other.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from kafriada.contexts.access import phone as phone_mod
from kafriada.contexts.audit.service import Actor, record
from kafriada.db.engine import transaction
from kafriada.settings import get_settings


class AppointRefused(Exception):
    """The appointment cannot be made, and the operator is told why."""


def appoint_super_admin(phone: str, reason: str) -> str:
    """Grant ``super_admin`` to the person registered with ``phone``. Returns their name."""
    reason = reason.strip()
    if not reason:
        raise AppointRefused("Say why. It is kept in the audit log.")
    try:
        e164 = phone_mod.normalise(phone)
    except phone_mod.InvalidPhoneNumberError as exc:
        raise AppointRefused(str(exc)) from exc

    with transaction() as session:
        user = session.execute(
            text(
                "SELECT id, full_name, phone_verified_at, email_verified_at FROM ops.users "
                "WHERE phone_e164 = :p AND anonymised_at IS NULL"
            ),
            {"p": e164},
        ).mappings().one_or_none()
        if user is None:
            raise AppointRefused("Nobody has registered with that number. They must register first.")
        cfg = get_settings()
        if cfg.require_phone_confirmation and user["phone_verified_at"] is None:
            raise AppointRefused("That number has not been confirmed yet. They must confirm it first.")
        if cfg.require_email_confirmation and user["email_verified_at"] is None:
            raise AppointRefused("Their email has not been confirmed yet. They must confirm it first.")
        held = session.execute(
            text(
                "SELECT 1 FROM ops.user_roles WHERE user_id = :u AND role_code = 'super_admin' "
                "AND revoked_at IS NULL"
            ),
            {"u": user["id"]},
        ).first()
        if held is not None:
            raise AppointRefused(f"{user['full_name']} is already a super administrator.")
        session.execute(
            text(
                "INSERT INTO ops.user_roles (user_id, role_code, scope_kind, scope_id, reason) "
                "VALUES (:u, 'super_admin', 'global', NULL, :r)"
            ),
            {"u": user["id"], "r": f"appointed by the operator: {reason}"[:300]},
        )
        record(
            session,
            actor=Actor.system("operator"),
            action="role.granted",
            subject_type="user",
            subject_id=str(user["id"]),
            metadata={"role": "super_admin", "how": "operator command", "reason": reason},
        )
    return str(user["full_name"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Appoint the first super administrator.")
    parser.add_argument("--phone", required=True, help="the phone number they registered with")
    parser.add_argument("--reason", required=True, help="why; written to the audit log")
    args = parser.parse_args()
    try:
        name = appoint_super_admin(args.phone, args.reason)
    except AppointRefused as exc:
        sys.stderr.write(f"Not appointed: {exc}\n")
        return 1
    sys.stdout.write(f"{name} is now a super administrator.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

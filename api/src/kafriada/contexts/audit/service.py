"""Audit — the record of what happened.

The only way anything in this system writes to ``ops.audit_log``. Everything
else calls :func:`record`.

Two rules, both learned the expensive way in systems that did not have them:

**An audit row joins the caller's transaction.** It takes the session it is given
rather than opening its own. If the business change rolls back, so does the
record of it — otherwise the log fills with events that never happened, and a log
that describes things that did not occur is worse than no log, because people
believe it.

**Writing the log must not be able to fail the operation.** The row is written
inside the same transaction, so a genuine database error will roll everything
back — that is correct. What is not correct is a *formatting* mistake, a value
that will not serialise, taking down a registration. So the payload is coerced
into something safe before it goes anywhere near the database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)

# Anything whose name suggests a secret is dropped before it reaches the row.
# Audit metadata is read by coordinators and exported for disputes; a one-time
# code or a token sitting in it would be a leak with a long tail.
_FORBIDDEN_KEYS = (
    "password", "token", "secret", "otp", "pin", "authorization",
    "cookie", "session", "api_key", "card", "cvv",
)

MAX_METADATA_BYTES = 8_192


@dataclass(frozen=True, slots=True)
class Actor:
    """Who did the thing.

    ``label`` is stored as plain text alongside the id, and outlives it. When a
    person exercises their right to erasure their user row is anonymised, and an
    audit trail that then said only "user 4f3a…" would have lost its subject.
    """

    user_id: UUID | None
    label: str
    role: str | None = None

    @classmethod
    def system(cls, reason: str) -> Actor:
        """For scheduled jobs and provider webhooks — nobody pressed a button."""
        return cls(user_id=None, label=f"system:{reason}", role="system")


def record(
    session: Session,
    *,
    actor: Actor,
    action: str,
    subject_type: str,
    subject_id: str,
    metadata: dict[str, Any] | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
) -> None:
    """Write one audit row into the caller's transaction.

    ``action`` is a dotted verb in the past tense — ``athlete.registered``,
    ``verification.approved``, ``payment.confirmed`` — so the log reads as a
    history rather than a list of function calls.
    """
    session.execute(
        text(
            """
            INSERT INTO ops.audit_log
                (actor_user_id, actor_label, actor_role, action,
                 subject_type, subject_id, request_id, ip_address, metadata)
            VALUES
                (:actor_user_id, :actor_label, :actor_role, :action,
                 :subject_type, :subject_id, :request_id,
                 CAST(:ip_address AS inet), CAST(:metadata AS jsonb))
            """
        ),
        {
            "actor_user_id": actor.user_id,
            "actor_label": actor.label[:200],
            "actor_role": actor.role,
            "action": action,
            "subject_type": subject_type,
            "subject_id": str(subject_id)[:200],
            "request_id": request_id,
            "ip_address": ip_address,
            "metadata": _safe_metadata(metadata),
        },
    )


def _safe_metadata(metadata: dict[str, Any] | None) -> str:
    """Turn arbitrary values into JSON that cannot break the insert.

    Drops anything that looks like a secret, coerces values JSON cannot express,
    and truncates. A registration must never fail because someone put an
    unusual object in a debug field.
    """
    if not metadata:
        return "{}"

    cleaned: dict[str, Any] = {}
    for key, value in metadata.items():
        if any(word in key.lower() for word in _FORBIDDEN_KEYS):
            cleaned[key] = "[redacted]"
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[key] = value
        elif isinstance(value, UUID):
            cleaned[key] = str(value)
        else:
            cleaned[key] = str(value)[:500]

    encoded = json.dumps(cleaned, default=str, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_METADATA_BYTES:
        log.warning("audit_metadata_truncated", action_keys=sorted(cleaned))
        return json.dumps({"truncated": True, "keys": sorted(cleaned)})
    return encoded

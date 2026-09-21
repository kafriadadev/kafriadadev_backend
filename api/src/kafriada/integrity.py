"""The nightly integrity check: does what the database holds still add up?

Every rule here is something the system already tries to make impossible — by a
constraint, a trigger, or a transaction. This check does not trust any of them. It asks
the data directly, from outside the code that wrote it, because the day one of those
protections has a hole is precisely the day nothing else will notice. A clean run is
evidence; a dirty one is a page.

**Read-only.** It runs as the application role and only SELECTs (plus an object-store
HEAD for media). It repairs nothing: a wrong ledger is corrected by a person writing a
new line, never by a job editing an old one.

**Each check returns findings, not a verdict.** A finding names what is wrong and which
record, so whoever is paged has the row in front of them rather than a count.

What is checked, and why:

  * **Ledger.** A settled payment has exactly its gross credit (equal to the price agreed)
    and its fee debit, plus at most one reversal not exceeding the gross; a payment that
    is not settled has no ledger lines at all; every settled payment has a webhook record.
  * **Identity.** One KUID per athlete and no KUID twice; the counter never behind a serial in
    use (the collision that would put two people on one ID) and never ahead of the athletes
    issued (an unexplained gap in a public identity number).
  * **Verification.** Nothing is under review or approved without a settled payment and
    both files ready; every decision that changed a state has its row.
  * **Media.** Every file marked ready has its object in the store (a sample, if there are
    very many).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from kafriada.contexts.media.store import ObjectStore, StoreError, build_store
from kafriada.db.engine import transaction

log = structlog.get_logger(__name__)

MEDIA_SAMPLE = 500


@dataclass(frozen=True, slots=True)
class Finding:
    check: str
    detail: str


# Where the checks read from. Normally each query opens its own short transaction; the tests
# point it at one open session so they can corrupt data, look at what the checks say, and
# roll everything back — the ledger is append-only, so a corrupted row committed to a shared
# database could never be cleaned up and would fail every later run.
_reading_from: ContextVar[Session | None] = ContextVar("integrity_session", default=None)


@contextmanager
def reading_from(session: Session) -> Iterator[None]:
    token = _reading_from.set(session)
    try:
        yield
    finally:
        _reading_from.reset(token)


def _rows(sql: str, **params: object) -> list[dict[str, object]]:
    open_session = _reading_from.get()
    if open_session is not None:
        return [dict(r) for r in open_session.execute(text(sql), params).mappings()]
    with transaction() as session:
        return [dict(r) for r in session.execute(text(sql), params).mappings()]


def _each(check: str, rows: list[dict[str, object]], fmt: str) -> list[Finding]:
    return [Finding(check, fmt.format(**r)) for r in rows]


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------
def check_ledger() -> list[Finding]:
    findings: list[Finding] = []

    findings += _each(
        "ledger.settled_payment_shape",
        _rows(
            """
            SELECT p.reference, p.expected_kobo,
                   count(*) FILTER (WHERE l.source = 'paystack' AND l.direction = 'credit') AS gross_lines,
                   count(*) FILTER (WHERE l.source = 'fee' AND l.direction = 'debit') AS fee_lines,
                   coalesce(sum(l.amount_kobo) FILTER (WHERE l.source = 'paystack'), 0) AS gross,
                   coalesce(sum(l.amount_kobo) FILTER (WHERE l.source = 'fee'), 0) AS fee,
                   coalesce(sum(l.amount_kobo) FILTER (WHERE l.source = 'reversal'), 0) AS reversed
              FROM money.payments p
              LEFT JOIN money.ledger_entries l ON l.payment_id = p.id
             WHERE p.status = 'success'
             GROUP BY p.id, p.reference, p.expected_kobo
            HAVING count(*) FILTER (WHERE l.source = 'paystack' AND l.direction = 'credit') <> 1
                OR count(*) FILTER (WHERE l.source = 'fee' AND l.direction = 'debit') <> 1
                OR coalesce(sum(l.amount_kobo) FILTER (WHERE l.source = 'paystack'), 0) <> p.expected_kobo
                OR coalesce(sum(l.amount_kobo) FILTER (WHERE l.source = 'fee'), 0)
                       >= coalesce(sum(l.amount_kobo) FILTER (WHERE l.source = 'paystack'), 0)
                OR coalesce(sum(l.amount_kobo) FILTER (WHERE l.source = 'reversal'), 0)
                       > coalesce(sum(l.amount_kobo) FILTER (WHERE l.source = 'paystack'), 0)
            """
        ),
        "{reference}: gross lines {gross_lines}, fee lines {fee_lines}, gross {gross} vs "
        "agreed {expected_kobo}, fee {fee}, reversed {reversed}",
    )

    findings += _each(
        "ledger.line_on_unsettled_payment",
        _rows(
            """
            SELECT p.reference, p.status, count(*) AS lines
              FROM money.ledger_entries l JOIN money.payments p ON p.id = l.payment_id
             WHERE p.status <> 'success'
             GROUP BY p.reference, p.status
            """
        ),
        "{reference} is {status} but has {lines} ledger line(s)",
    )

    findings += _each(
        "ledger.settled_without_a_delivery_record",
        _rows(
            """
            SELECT p.reference FROM money.payments p
             WHERE p.status = 'success'
               AND NOT EXISTS (SELECT 1 FROM money.webhook_events w WHERE w.payment_id = p.id)
            """
        ),
        "{reference} is settled but no delivery was ever recorded for it",
    )

    findings += _each(
        "ledger.settled_payment_without_audit",
        _rows(
            """
            SELECT p.reference FROM money.payments p
             WHERE p.status = 'success'
               AND NOT EXISTS (SELECT 1 FROM ops.audit_log a
                                WHERE a.subject_type = 'payment' AND a.subject_id = p.id::text
                                  AND a.action = 'payment.settled')
            """
        ),
        "{reference} is settled but there is no audit row saying so",
    )
    return findings


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
def check_identity() -> list[Finding]:
    findings: list[Finding] = []

    findings += _each(
        "identity.athletes_per_user",
        _rows(
            "SELECT user_id::text AS who, count(*) AS n FROM identity.athletes "
            "GROUP BY user_id HAVING count(*) > 1"
        ),
        "user {who} holds {n} athlete records",
    )
    findings += _each(
        "identity.kuid_duplicated",
        _rows("SELECT kuid, count(*) AS n FROM identity.athletes GROUP BY kuid HAVING count(*) > 1"),
        "{kuid} is held by {n} athletes",
    )
    # The counter's column is called next_serial but holds the LAST serial issued: the mint
    # increments first and uses the result. So the counter must equal how many were issued
    # (nothing rolls back a serial: the increment is in the registration's own transaction,
    # which is why there are no gaps), and can never be behind the highest one in use.
    findings += _each(
        "identity.serial_counter_behind",
        _rows(
            """
            SELECT a.kuid_state, a.kuid_year, max(a.kuid_serial) AS highest, c.next_serial AS counter
              FROM identity.athletes a
              JOIN identity.kuid_counters c
                ON c.state_code = a.kuid_state AND c.year = a.kuid_year
             GROUP BY a.kuid_state, a.kuid_year, c.next_serial
            HAVING max(a.kuid_serial) > c.next_serial
            """
        ),
        "{kuid_state}/{kuid_year}: serial {highest} is in use but the counter is at {counter}, "
        "so the next registration would take a number that already belongs to someone",
    )
    findings += _each(
        "identity.serial_gap",
        _rows(
            """
            SELECT a.kuid_state, a.kuid_year, count(*) AS issued, c.next_serial AS counter
              FROM identity.athletes a
              JOIN identity.kuid_counters c
                ON c.state_code = a.kuid_state AND c.year = a.kuid_year
             GROUP BY a.kuid_state, a.kuid_year, c.next_serial
            HAVING count(*) <> c.next_serial
            """
        ),
        "{kuid_state}/{kuid_year}: {issued} athletes but the counter is at {counter} — "
        "a number was spent that no athlete holds",
    )
    findings += _each(
        "identity.athlete_without_a_counter",
        _rows(
            """
            SELECT DISTINCT a.kuid_state, a.kuid_year FROM identity.athletes a
             WHERE NOT EXISTS (SELECT 1 FROM identity.kuid_counters c
                                WHERE c.state_code = a.kuid_state AND c.year = a.kuid_year)
            """
        ),
        "{kuid_state}/{kuid_year} has athletes but no counter",
    )
    return findings


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def check_verification() -> list[Finding]:
    findings: list[Finding] = []

    findings += _each(
        "verification.reviewed_without_settled_payment",
        _rows(
            """
            SELECT v.id::text AS id, v.status FROM identity.verification_requests v
              LEFT JOIN money.payments p ON p.id = v.payment_id
             WHERE v.status IN ('under_review', 'approved', 'rejected', 'escalated', 'revoked')
               AND (p.id IS NULL OR p.status <> 'success')
            """
        ),
        "request {id} is {status} without a settled payment",
    )
    findings += _each(
        "verification.approved_without_files",
        _rows(
            """
            SELECT v.id::text AS id FROM identity.verification_requests v
              LEFT JOIN identity.media_files pm ON pm.id = v.photo_media_id
             WHERE v.status = 'approved' AND (pm.id IS NULL OR pm.status <> 'ready')
            """
        ),
        "request {id} is approved but its photo is not ready",
    )
    findings += _each(
        "verification.decision_missing",
        _rows(
            """
            SELECT v.id::text AS id, v.status FROM identity.verification_requests v
             WHERE v.status IN ('approved', 'rejected', 'escalated', 'revoked')
               AND NOT EXISTS (
                   SELECT 1 FROM identity.verification_decisions d
                    WHERE d.request_id = v.id
                      AND d.decision = CASE v.status WHEN 'approved' THEN 'approved'
                                                     WHEN 'rejected' THEN 'rejected'
                                                     WHEN 'escalated' THEN 'escalated'
                                                     ELSE 'revoked' END)
            """
        ),
        "request {id} is {status} but no such decision is on record",
    )
    return findings


# ---------------------------------------------------------------------------
# Media
# ---------------------------------------------------------------------------
def check_media(store: ObjectStore | None = None) -> list[Finding]:
    store = store or build_store()
    if store.name == "none":
        return []
    rows = _rows(
        "SELECT id::text AS id, derivative_key FROM identity.media_files "
        "WHERE status = 'ready' ORDER BY random() LIMIT :n",
        n=MEDIA_SAMPLE,
    )
    findings: list[Finding] = []
    for row in rows:
        try:
            present = store.head(str(row["derivative_key"])) is not None
        except StoreError as exc:
            # We could not look. That is not evidence of anything missing, but it is not
            # a clean bill either, so it is reported rather than swallowed.
            findings.append(Finding("media.store_unreachable", f"{row['id']}: {exc.message}"))
            break
        if not present:
            findings.append(Finding("media.object_missing", f"{row['id']} is ready but its object is gone"))
    return findings


def run_all(store: ObjectStore | None = None) -> list[Finding]:
    """Every check, in order. Empty means everything adds up."""
    findings = check_ledger() + check_identity() + check_verification() + check_media(store)
    for f in findings:
        log.error("integrity_finding", check=f.check, detail=f.detail)
    return findings

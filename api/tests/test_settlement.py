"""Settlement and the ledger's guarantees, proved against a real database.

What is proved here:
  - a matching charge writes exactly two ledger lines, marks the payment paid and
    leaves an audit row — all in one commit
  - the same delivery, five copies at the same instant, still leaves exactly two
    ledger lines (the duplicate check is the database's, not a read)
  - a wrong amount, currency or missing fee freezes: no ledger line, an audit row,
    an error-level log — and never a success
  - a late payment on an abandoned or failed attempt is a success
  - if anything fails midway nothing is left behind, including the "seen" mark
  - ``kaf_app`` cannot write the ledger; nobody — ``kaf_money`` and the object
    owner included — can update, delete or truncate a ledger line

Rows are left behind, like every other DB test here: the ledger is append-only.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from kafriada.contexts.ledger.entries import InvalidAmount
from kafriada.contexts.payments import settlement
from kafriada.contexts.payments.rules import (
    ChargeEvent,
    PaymentStatus,
    Purpose,
    new_reference,
)
from kafriada.contexts.payments.settlement import Outcome, settle_charge
from kafriada.db.engine import money_transaction
from tests._access_helpers import make_user
from tests._payment_helpers import record_logs

URLS = {
    name: os.environ.get(f"DATABASE_URL_{name.upper()}")
    for name in ("app", "money", "migrate")
}

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not all(URLS.values()),
        reason="needs DATABASE_URL_APP, DATABASE_URL_MONEY and DATABASE_URL_MIGRATE",
    ),
]

PRICE = 250_000  # 2,500 naira
FEE = 3_750  # 37.50 naira


@pytest.fixture(scope="module")
def payer() -> UUID:
    user_id, _ = make_user("Payer")
    return user_id


@pytest.fixture(scope="module")
def engines() -> Iterator[dict[str, object]]:
    made = {n: create_engine(u or "", future=True, connect_args={"connect_timeout": 30})
            for n, u in URLS.items()}
    yield made  # type: ignore[misc]
    for engine in made.values():
        engine.dispose()


def make_payment(payer: UUID, *, status: str = "pending", expected: int = PRICE) -> str:
    """A payment as the initialise step will create it. Returns its reference."""
    ref = new_reference()
    with money_transaction(reason="test fixture: create payment") as session:
        session.execute(
            text(
                """
                INSERT INTO money.payments (reference, purpose, expected_kobo, status, paid_by)
                VALUES (:ref, :purpose, :expected, :status, :payer)
                """
            ),
            {
                "ref": ref,
                "purpose": Purpose.STAGE2_ATHLETE.value,
                "expected": expected,
                "status": status,
                "payer": payer,
            },
        )
    return ref


def charge(ref: str, **overrides: object) -> ChargeEvent:
    fields: dict[str, object] = {
        "reference": ref,
        "amount_kobo": PRICE,
        "currency": "NGN",
        "status": "success",
        "fees_kobo": FEE,
    }
    fields.update(overrides)
    return ChargeEvent(**fields)  # type: ignore[arg-type]


def ledger_for(ref: str) -> list[tuple[str, str, int]]:
    with money_transaction(reason="test: read ledger") as session:
        rows = session.execute(
            text(
                """
                SELECT l.direction, l.source, l.amount_kobo
                FROM money.ledger_entries l JOIN money.payments p ON p.id = l.payment_id
                WHERE p.reference = :ref ORDER BY l.source
                """
            ),
            {"ref": ref},
        ).all()
    return [(r.direction, r.source, r.amount_kobo) for r in rows]


def status_of(ref: str) -> str:
    with money_transaction(reason="test: read status") as session:
        return str(
            session.execute(
                text("SELECT status FROM money.payments WHERE reference = :r"), {"r": ref}
            ).scalar_one()
        )


def audit_actions(payment_id: UUID) -> list[str]:
    with money_transaction(reason="test: read audit") as session:
        return [
            r.action
            for r in session.execute(
                text(
                    "SELECT action FROM ops.audit_log "
                    "WHERE subject_type = 'payment' AND subject_id = :i ORDER BY id"
                ),
                {"i": str(payment_id)},
            )
        ]


def seen_count(ref: str) -> int:
    with money_transaction(reason="test: read webhook_events") as session:
        return int(
            session.execute(
                text("SELECT count(*) FROM money.webhook_events WHERE event_key LIKE :k"),
                {"k": f"%{ref}"},
            ).scalar_one()
        )


class TestSettling:
    def test_a_matching_charge_writes_exactly_two_lines_and_marks_it_paid(
        self, payer: UUID
    ) -> None:
        ref = make_payment(payer)
        result = settle_charge(charge(ref))

        assert result.outcome is Outcome.SETTLED
        assert ledger_for(ref) == [("debit", "fee", FEE), ("credit", "paystack", PRICE)]
        assert status_of(ref) == "success"
        assert result.payment_id is not None
        assert audit_actions(result.payment_id) == ["payment.settled"]

    @pytest.mark.parametrize("earlier", ["abandoned", "failed"])
    def test_a_late_payment_beats_an_earlier_giving_up(self, payer: UUID, earlier: str) -> None:
        ref = make_payment(payer, status=earlier)
        assert settle_charge(charge(ref)).outcome is Outcome.SETTLED
        assert status_of(ref) == "success"
        assert len(ledger_for(ref)) == 2

    def test_someone_elses_reference_is_ignored_without_touching_the_database(self) -> None:
        assert settle_charge(charge("order-8841")).outcome is Outcome.IGNORED

    def test_an_unknown_kaf_reference_writes_nothing_and_stays_retryable(
        self, payer: UUID, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ref = new_reference()  # no payment row yet
        logs = record_logs(monkeypatch, settlement)
        assert settle_charge(charge(ref)).outcome is Outcome.UNKNOWN
        assert logs.errors() == ["payment_reference_unknown"]
        monkeypatch.undo()
        assert seen_count(ref) == 0

        # The row becomes visible; the same delivery, retried, now settles.
        with money_transaction(reason="test fixture: late payment row") as session:
            session.execute(
                text(
                    "INSERT INTO money.payments (reference, purpose, expected_kobo, paid_by) "
                    "VALUES (:r, 'stage2_athlete', :e, :p)"
                ),
                {"r": ref, "e": PRICE, "p": payer},
            )
        assert settle_charge(charge(ref)).outcome is Outcome.SETTLED


class TestReplay:
    def test_the_same_delivery_twice_in_a_row_writes_once(self, payer: UUID) -> None:
        ref = make_payment(payer)
        assert settle_charge(charge(ref)).outcome is Outcome.SETTLED
        assert settle_charge(charge(ref)).outcome is Outcome.DUPLICATE
        assert len(ledger_for(ref)) == 2

    def test_five_copies_at_the_same_instant_leave_exactly_two_ledger_rows(
        self, payer: UUID
    ) -> None:
        # Several rounds: one lucky round proves nothing about a race.
        for _ in range(6):
            ref = make_payment(payer)
            copies = 5
            barrier = threading.Barrier(copies)

            def deliver(_: int, ref: str = ref, barrier: threading.Barrier = barrier) -> Outcome:
                barrier.wait()
                return settle_charge(charge(ref)).outcome

            with ThreadPoolExecutor(max_workers=copies) as pool:
                outcomes = list(pool.map(deliver, range(copies)))

            assert sorted(outcomes) == sorted([Outcome.SETTLED] + [Outcome.DUPLICATE] * 4)
            assert len(ledger_for(ref)) == 2
            assert status_of(ref) == "success"
            assert seen_count(ref) == 1


class TestFreezing:
    def test_ten_naira_never_buys_a_2500_naira_badge(
        self, payer: UUID, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ref = make_payment(payer)
        logs = record_logs(monkeypatch, settlement)
        result = settle_charge(charge(ref, amount_kobo=1_000, fees_kobo=15))

        assert result.outcome is Outcome.FROZEN
        assert status_of(ref) == "frozen"
        assert ledger_for(ref) == []
        assert result.payment_id is not None
        assert audit_actions(result.payment_id) == ["payment.frozen"]
        assert logs.errors() == ["payment_frozen"]

    @pytest.mark.parametrize(
        "overrides",
        [
            {"amount_kobo": PRICE + 1},  # overpaying is as suspect as underpaying
            {"currency": "USD"},
            {"status": "failed"},
            {"fees_kobo": None},
        ],
    )
    def test_anything_that_does_not_match_exactly_is_frozen(
        self, payer: UUID, overrides: dict[str, object]
    ) -> None:
        ref = make_payment(payer)
        assert settle_charge(charge(ref, **overrides)).outcome is Outcome.FROZEN
        assert status_of(ref) == "frozen"
        assert ledger_for(ref) == []

    def test_the_amount_is_compared_to_the_price_recorded_on_the_payment(
        self, payer: UUID
    ) -> None:
        ref = make_payment(payer, expected=1_500_000)  # a club's price
        assert settle_charge(charge(ref)).outcome is Outcome.FROZEN

    def test_a_replayed_freeze_is_not_frozen_twice(self, payer: UUID) -> None:
        ref = make_payment(payer)
        assert settle_charge(charge(ref, amount_kobo=1_000, fees_kobo=15)).outcome is Outcome.FROZEN
        assert settle_charge(charge(ref, amount_kobo=1_000, fees_kobo=15)).outcome is Outcome.DUPLICATE
        assert seen_count(ref) == 1


class TestOneTransaction:
    def test_a_failure_midway_leaves_nothing_behind_not_even_the_seen_mark(
        self, payer: UUID, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ref = make_payment(payer)

        def boom(**_: object) -> None:
            raise InvalidAmount("simulated failure after the duplicate check")

        monkeypatch.setattr(settlement, "plan_settlement", boom)
        with pytest.raises(InvalidAmount):
            settle_charge(charge(ref))
        monkeypatch.undo()

        assert status_of(ref) == "pending"
        assert ledger_for(ref) == []
        assert seen_count(ref) == 0
        # And the redelivery Paystack will send now succeeds.
        assert settle_charge(charge(ref)).outcome is Outcome.SETTLED


class TestLedgerPrivileges:
    def _fails(self, engine: object, sql: str, params: dict[str, object] | None = None) -> str:
        with pytest.raises((DBAPIError, IntegrityError)) as caught:
            with engine.begin() as conn:  # type: ignore[attr-defined]
                conn.execute(text(sql), params or {})
        return str(caught.value).lower()

    @pytest.fixture
    def settled_line(self, payer: UUID) -> int:
        ref = make_payment(payer)
        settle_charge(charge(ref))
        with money_transaction(reason="test: find a ledger line") as session:
            return int(
                session.execute(
                    text(
                        "SELECT l.id FROM money.ledger_entries l "
                        "JOIN money.payments p ON p.id = l.payment_id "
                        "WHERE p.reference = :r AND l.source = 'paystack'"
                    ),
                    {"r": ref},
                ).scalar_one()
            )

    def test_the_application_role_cannot_insert_a_ledger_row(
        self, engines: dict[str, object], payer: UUID
    ) -> None:
        ref = make_payment(payer)
        with money_transaction(reason="test: payment id") as session:
            pid = session.execute(
                text("SELECT id FROM money.payments WHERE reference = :r"), {"r": ref}
            ).scalar_one()
        message = self._fails(
            engines["app"],
            # An explicit id, so the refusal cannot come from the sequence: it
            # must be the table's grant that says no.
            "INSERT INTO money.ledger_entries (id, payment_id, direction, source, amount_kobo) "
            "VALUES (9000000000000000, :p, 'credit', 'paystack', 250000)",
            {"p": pid},
        )
        assert "permission denied for table ledger_entries" in message
        assert ledger_for(ref) == []

    def test_the_application_role_cannot_settle_a_payment_by_hand(
        self, engines: dict[str, object], payer: UUID
    ) -> None:
        ref = make_payment(payer)
        message = self._fails(
            engines["app"],
            "UPDATE money.payments SET status = 'success' WHERE reference = :r",
            {"r": ref},
        )
        assert "permission denied" in message

    def test_the_application_role_can_read_the_ledger(
        self, engines: dict[str, object], settled_line: int
    ) -> None:
        with engines["app"].begin() as conn:  # type: ignore[attr-defined]
            assert conn.execute(
                text("SELECT count(*) FROM money.ledger_entries WHERE id = :i"), {"i": settled_line}
            ).scalar_one() == 1

    @pytest.mark.parametrize("role", ["money", "migrate"])
    @pytest.mark.parametrize(
        "sql",
        [
            "UPDATE money.ledger_entries SET amount_kobo = 1 WHERE id = :i",
            "DELETE FROM money.ledger_entries WHERE id = :i",
            "TRUNCATE money.ledger_entries",
        ],
    )
    def test_nobody_can_edit_or_remove_a_ledger_line(
        self, engines: dict[str, object], settled_line: int, role: str, sql: str
    ) -> None:
        # money: refused by privilege. migrate owns the table: refused by trigger.
        message = self._fails(engines[role], sql, {"i": settled_line} if ":i" in sql else {})
        assert "permission denied" in message or "append-only" in message
        with money_transaction(reason="test: still there") as session:
            assert session.execute(
                text("SELECT count(*) FROM money.ledger_entries WHERE id = :i"),
                {"i": settled_line},
            ).scalar_one() == 1

    def test_the_owner_is_stopped_by_the_trigger_not_just_by_privilege(
        self, engines: dict[str, object], settled_line: int
    ) -> None:
        message = self._fails(
            engines["migrate"], "DELETE FROM money.ledger_entries WHERE id = :i", {"i": settled_line}
        )
        assert "append-only" in message

    def test_the_seen_record_is_insert_only_too(
        self, engines: dict[str, object], settled_line: int
    ) -> None:
        for role in ("money", "migrate"):
            message = self._fails(engines[role], "DELETE FROM money.webhook_events")
            assert "permission denied" in message or "append-only" in message
        for sql in (
            "UPDATE money.webhook_events SET event_key = 'x'",
            "TRUNCATE money.webhook_events",
        ):
            message = self._fails(engines["migrate"], sql)
            assert "append-only" in message

    def test_exactly_two_lines_per_payment_is_structural(
        self, engines: dict[str, object], payer: UUID
    ) -> None:
        ref = make_payment(payer)
        settle_charge(charge(ref))
        with money_transaction(reason="test: payment id") as session:
            pid = session.execute(
                text("SELECT id FROM money.payments WHERE reference = :r"), {"r": ref}
            ).scalar_one()
        message = self._fails(
            engines["money"],
            "INSERT INTO money.ledger_entries (payment_id, direction, source, amount_kobo) "
            "VALUES (:p, 'credit', 'paystack', 250000)",
            {"p": pid},
        )
        assert "ledger_one_line_per_source" in message
        assert len(ledger_for(ref)) == 2


class TestPaymentGuard:
    def test_what_was_agreed_to_be_paid_cannot_be_changed(
        self, engines: dict[str, object], payer: UUID
    ) -> None:
        ref = make_payment(payer)
        with pytest.raises(DBAPIError) as caught:
            with engines["money"].begin() as conn:  # type: ignore[attr-defined]
                conn.execute(
                    text("UPDATE money.payments SET expected_kobo = 1000 WHERE reference = :r"),
                    {"r": ref},
                )
        assert "immutable" in str(caught.value)

    def test_a_settled_payment_is_final(self, engines: dict[str, object], payer: UUID) -> None:
        ref = make_payment(payer)
        settle_charge(charge(ref))
        with pytest.raises(DBAPIError) as caught:
            with engines["money"].begin() as conn:  # type: ignore[attr-defined]
                conn.execute(
                    text("UPDATE money.payments SET status = 'failed' WHERE reference = :r"),
                    {"r": ref},
                )
        assert "final" in str(caught.value)
        assert status_of(ref) == PaymentStatus.SUCCESS.value

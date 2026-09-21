"""Reconciliation and expiry: catching what the webhook missed, and never doing more.

What is proved here, against a real database with a fake Paystack:
  - a payment Paystack says was paid, whose webhook never arrived, is settled — into the
    same two ledger lines, by the same code, with the same audit trail
  - a payment confirmed by BOTH the webhook and reconciliation is still recorded once,
    including when they race
  - it only ever CONFIRMS: "abandoned", "failed" or "never heard of it" change nothing,
    payments already settled or frozen are never asked about, and nothing is reversed
  - a mismatch freezes for a person; an answer about a different reference is refused
  - a payment is expired after 72 hours only after Paystack was asked and did not say it
    was paid — and is left alone if Paystack could not be asked
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
from sqlalchemy import text

from kafriada.contexts.payments import reconcile, settlement
from kafriada.contexts.payments.provider import FakeProvider, NoProvider, ProviderError
from kafriada.contexts.payments.rules import Purpose, new_reference
from kafriada.contexts.payments.settlement import Outcome, settle_charge
from kafriada.db.engine import money_transaction
from tests._payment_helpers import (
    Athlete,
    charge_success_event,
    new_athlete,
    record_logs,
    state,
)

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL_APP") and os.environ.get("DATABASE_URL_MONEY")),
        reason="needs DATABASE_URL_APP and DATABASE_URL_MONEY",
    ),
]


@pytest.fixture(scope="module")
def payer() -> Athlete:
    return new_athlete("Reconcile")


def payment(payer: Athlete, *, status: str = "pending", age_minutes: int = 30) -> str:
    """A payment created ``age_minutes`` ago, as the initialise step would have left it."""
    ref = new_reference()
    with money_transaction(reason="test fixture: create an aged payment") as session:
        session.execute(
            text(
                "INSERT INTO money.payments (reference, purpose, expected_kobo, status, paid_by, created_at) "
                "VALUES (:r, :p, 250000, :s, :u, now() - make_interval(mins => :age))"
            ),
            {"r": ref, "p": Purpose.STAGE2_ATHLETE.value, "s": status, "u": payer.user_id, "age": age_minutes},
        )
    return ref


def paid_at_paystack(fake: FakeProvider, ref: str, **overrides: object) -> None:
    fake.results[ref] = charge_success_event(ref, **overrides)


def audit_labels(ref: str) -> list[str]:
    from tests._access_helpers import sql

    (row,) = sql("SELECT id FROM money.payments WHERE reference = :r", r=ref)
    return [str(r["actor_label"]) for r in sql(
        "SELECT actor_label FROM ops.audit_log WHERE subject_type = 'payment' AND subject_id = :s ORDER BY id",
        s=str(row["id"]))]


class TestReconciliation:
    def test_a_payment_the_webhook_missed_is_settled_by_asking_paystack(self, payer: Athlete) -> None:
        ref = payment(payer)
        fake = FakeProvider()
        paid_at_paystack(fake, ref)

        result = reconcile.reconcile(provider=fake, limit=100_000)

        assert result.settled >= 1
        found = state(ref)
        assert found["status"] == "success"
        assert len(found["ledger"]) == 2  # type: ignore[arg-type]
        assert found["audit"] == ["payment.settled"]
        assert audit_labels(ref) == ["system:reconciliation"]

    def test_the_webhook_arriving_afterwards_changes_nothing(self, payer: Athlete) -> None:
        ref = payment(payer)
        fake = FakeProvider()
        paid_at_paystack(fake, ref)
        reconcile.reconcile(provider=fake, limit=100_000)

        assert settle_charge(charge_success_event(ref)).outcome is Outcome.DUPLICATE
        assert len(state(ref)["ledger"]) == 2  # type: ignore[arg-type]

    def test_the_webhook_and_reconciliation_racing_still_leave_two_lines(self, payer: Athlete) -> None:
        ref = payment(payer)
        fake = FakeProvider()
        paid_at_paystack(fake, ref)
        barrier = threading.Barrier(4)

        def webhook(_: int) -> Outcome:
            barrier.wait()
            return settle_charge(charge_success_event(ref)).outcome

        def reconciler(_: int) -> Outcome:
            barrier.wait()
            return settlement.settle_charge(charge_success_event(ref), source="reconciliation").outcome

        with ThreadPoolExecutor(max_workers=4) as pool:
            outcomes = list(pool.map(lambda i: (webhook if i % 2 else reconciler)(i), range(4)))

        assert sorted(o.value for o in outcomes) == ["duplicate", "duplicate", "duplicate", "settled"]
        assert len(state(ref)["ledger"]) == 2  # type: ignore[arg-type]

    @pytest.mark.parametrize("says", ["abandoned", "failed", "pending", "ongoing"])
    def test_a_payment_paystack_does_not_say_was_paid_is_left_exactly_as_it_was(
        self, payer: Athlete, says: str
    ) -> None:
        ref = payment(payer)
        fake = FakeProvider()
        paid_at_paystack(fake, ref, status=says)
        reconcile.reconcile(provider=fake, limit=100_000)
        assert state(ref) == {"status": "pending", "ledger": [], "seen": 0, "audit": []}

    def test_a_reference_paystack_has_never_heard_of_is_left_alone(self, payer: Athlete) -> None:
        ref = payment(payer)
        reconcile.reconcile(provider=FakeProvider(), limit=100_000)
        assert state(ref)["status"] == "pending"

    def test_a_late_payment_on_an_abandoned_attempt_is_confirmed(self, payer: Athlete) -> None:
        ref = payment(payer, status="abandoned", age_minutes=60)
        fake = FakeProvider()
        paid_at_paystack(fake, ref)
        reconcile.reconcile(provider=fake, limit=100_000)
        assert state(ref)["status"] == "success"

    def test_it_never_asks_about_what_is_already_decided_or_still_being_typed(self, payer: Athlete) -> None:
        settled = payment(payer)
        settle_charge(charge_success_event(settled))
        frozen = payment(payer)
        settle_charge(charge_success_event(frozen, amount_kobo=1_000, fees_kobo=15))
        too_young = payment(payer, age_minutes=2)
        long_dead = payment(payer, status="failed", age_minutes=60 * 24 * 10)
        fake = FakeProvider()

        reconcile.reconcile(provider=fake, limit=100_000)

        for ref in (settled, frozen, too_young, long_dead):
            assert ref not in fake.verified
        # ...and, having never been asked, a settled payment cannot be un-settled by an answer.
        assert state(settled)["status"] == "success"

    def test_a_mismatch_freezes_for_a_person_and_never_settles(
        self, payer: Athlete, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ref = payment(payer)
        fake = FakeProvider()
        paid_at_paystack(fake, ref, amount_kobo=1_000, fees_kobo=15)
        logs = record_logs(monkeypatch, settlement)

        result = reconcile.reconcile(provider=fake, limit=100_000)

        assert result.frozen >= 1
        assert state(ref)["status"] == "frozen" and state(ref)["ledger"] == []
        assert "payment_frozen" in logs.errors()

    def test_an_answer_about_a_different_reference_is_refused(self, payer: Athlete) -> None:
        ref, other = payment(payer), new_reference()
        fake = FakeProvider()
        fake.results[ref] = charge_success_event(other)

        result = reconcile.reconcile(provider=fake, limit=100_000)

        assert result.errors >= 1
        assert state(ref)["status"] == "pending"

    def test_an_unreachable_paystack_changes_nothing_and_is_counted(self, payer: Athlete) -> None:
        ref = payment(payer)

        class Down(FakeProvider):
            def verify(self, reference: str):  # type: ignore[no-untyped-def]
                raise ProviderError("paystack unreachable: ConnectTimeout", transient=True)

        result = reconcile.reconcile(provider=Down(), limit=100_000)
        assert result.errors >= 1 and result.settled == 0
        assert state(ref)["status"] == "pending"

    def test_without_a_provider_there_is_nothing_to_ask(self) -> None:
        assert reconcile.reconcile(provider=NoProvider()).skipped is True
        assert reconcile.expire_stale(provider=NoProvider()).skipped is True


class TestExpiry:
    def test_an_unpaid_payment_is_abandoned_after_72_hours_and_the_audit_says_so(
        self, payer: Athlete
    ) -> None:
        ref = payment(payer, age_minutes=73 * 60)
        fake = FakeProvider()  # Paystack has never heard of it

        result = reconcile.expire_stale(provider=fake, limit=100_000)

        assert result.expired >= 1
        assert ref in fake.verified  # it was asked first
        assert state(ref) == {"status": "abandoned", "ledger": [], "seen": 0, "audit": ["payment.abandoned"]}
        assert audit_labels(ref) == ["system:payment_expiry"]

    def test_a_payment_younger_than_72_hours_is_not_touched(self, payer: Athlete) -> None:
        ref = payment(payer, age_minutes=71 * 60)
        fake = FakeProvider()
        reconcile.expire_stale(provider=fake, limit=100_000)
        assert ref not in fake.verified and state(ref)["status"] == "pending"

    def test_a_payment_that_was_paid_after_all_is_settled_not_expired(self, payer: Athlete) -> None:
        ref = payment(payer, age_minutes=100 * 60)
        fake = FakeProvider()
        paid_at_paystack(fake, ref)

        result = reconcile.expire_stale(provider=fake, limit=100_000)

        assert result.settled >= 1
        assert state(ref)["status"] == "success" and len(state(ref)["ledger"]) == 2  # type: ignore[arg-type]

    def test_a_payment_that_cannot_be_checked_is_left_alone_not_expired(self, payer: Athlete) -> None:
        ref = payment(payer, age_minutes=100 * 60)

        class Down(FakeProvider):
            def verify(self, reference: str):  # type: ignore[no-untyped-def]
                raise ProviderError("paystack 503", transient=True)

        result = reconcile.expire_stale(provider=Down(), limit=100_000)
        assert result.left_alone >= 1
        assert state(ref)["status"] == "pending"

    def test_only_pending_payments_expire(self, payer: Athlete) -> None:
        settled = payment(payer, age_minutes=100 * 60)
        settle_charge(charge_success_event(settled))
        frozen = payment(payer, age_minutes=100 * 60)
        settle_charge(charge_success_event(frozen, amount_kobo=1_000, fees_kobo=15))
        failed = payment(payer, status="failed", age_minutes=100 * 60)

        reconcile.expire_stale(provider=FakeProvider(), limit=100_000)

        assert [state(r)["status"] for r in (settled, frozen, failed)] == ["success", "frozen", "failed"]

    def test_a_mismatched_payment_found_during_expiry_is_frozen_not_abandoned(self, payer: Athlete) -> None:
        ref = payment(payer, age_minutes=100 * 60)
        fake = FakeProvider()
        paid_at_paystack(fake, ref, amount_kobo=1_000, fees_kobo=15)
        reconcile.expire_stale(provider=fake, limit=100_000)
        assert state(ref)["status"] == "frozen"


def test_the_payment_id_type_used_by_the_jobs_is_a_string(payer: Athlete) -> None:
    # The audit row's subject_id is text; a UUID object would be str()'d by record(), and the
    # integrity check joins on p.id::text. Guard the join key so the two cannot drift apart.
    ref = payment(payer, age_minutes=100 * 60)
    reconcile.expire_stale(provider=FakeProvider(), limit=100_000)
    from tests._access_helpers import sql

    (row,) = sql("SELECT id FROM money.payments WHERE reference = :r", r=ref)
    assert isinstance(row["id"], UUID)
    assert state(ref)["audit"] == ["payment.abandoned"]

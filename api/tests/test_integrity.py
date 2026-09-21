"""The nightly integrity check: quiet when the books add up, loud — and specific — when not.

What is proved here:
  - records produced by the real flows (a settled payment, a refund, an approved
    verification) raise no finding
  - each way the data could be wrong is reported, naming the record: a settled payment
    with the wrong lines, lines on an unsettled payment, a refund larger than the payment,
    a settlement nobody delivered or audited, a counter behind or ahead of the serials in
    use, a review nobody paid for, a decision that was never written, a photo whose
    object has gone missing

The corruptions are made inside a transaction that is ROLLED BACK. The ledger is
append-only, so a bad row committed to a shared database could never be removed and would
fail every later run; here the check is simply pointed at the open, uncommitted session.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from kafriada import integrity
from kafriada.contexts.media.store import LocalStore
from kafriada.contexts.payments.rules import Purpose, new_reference
from kafriada.db.engine import money_engine
from kafriada.main import create_app
from tests._access_helpers import sql
from tests._media_helpers import (
    LGA,
    athlete_with_files,
    pay,
    request_id_of,
    review_url,
    reviewer,
    use_local_store,
)
from tests._payment_helpers import Athlete, new_athlete

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL_APP") and os.environ.get("DATABASE_URL_MONEY")
             and os.environ.get("DATABASE_URL_MIGRATE")),
        reason="needs the app, money and migrate database URLs",
    ),
]


@pytest.fixture(scope="module")
def payer() -> Athlete:
    return new_athlete("Integrity")


@pytest.fixture
def scratch() -> Iterator[Session]:
    """An open session as the table owner whose every change is thrown away.

    The owner, not a working role: corrupting data needs privileges the application
    deliberately does not have (deleting a counter, editing a file's status). The ledger
    is still insert-only for the owner too — its trigger — but INSERT is all that needs.
    """
    engine = create_engine(os.environ["DATABASE_URL_MIGRATE"], future=True)
    session = Session(bind=engine, future=True)
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def checks(scratch: Session, *, only: str | None = None) -> list[str]:
    with integrity.reading_from(scratch):
        found = integrity.check_ledger() + integrity.check_identity() + integrity.check_verification()
    return [f"{f.check}: {f.detail}" for f in found if only is None or only in f.detail or only in f.check]


def payment(scratch: Session, payer: Athlete, status: str = "pending") -> str:
    ref = new_reference()
    scratch.execute(
        text(
            "INSERT INTO money.payments (reference, purpose, expected_kobo, paid_by) "
            "VALUES (:r, :p, 250000, :u)"
        ),
        {"r": ref, "p": Purpose.STAGE2_ATHLETE.value, "u": payer.user_id},
    )
    if status != "pending":
        scratch.execute(text("UPDATE money.payments SET status = :s WHERE reference = :r"), {"s": status, "r": ref})
    return ref


def line(scratch: Session, ref: str, direction: str, source: str, amount: int, **extra: object) -> None:
    scratch.execute(
        text(
            "INSERT INTO money.ledger_entries (payment_id, direction, source, amount_kobo, note, recorded_by) "
            "SELECT id, :d, :s, :a, :n, :by FROM money.payments WHERE reference = :r"
        ),
        {"d": direction, "s": source, "a": amount, "r": ref, "n": extra.get("note"), "by": extra.get("by")},
    )


def delivered_and_audited(scratch: Session, ref: str) -> None:
    scratch.execute(
        text("INSERT INTO money.webhook_events (provider, event_key, payment_id) "
             "SELECT 'paystack', 'charge.success:' || reference, id FROM money.payments WHERE reference = :r"),
        {"r": ref},
    )
    scratch.execute(
        text("INSERT INTO ops.audit_log (actor_label, action, subject_type, subject_id) "
             "SELECT 'test', 'payment.settled', 'payment', id::text FROM money.payments WHERE reference = :r"),
        {"r": ref},
    )


class TestRealRecordsAreClean:
    def test_a_settled_refunded_and_approved_life_raises_nothing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        use_local_store(monkeypatch, tmp_path)
        with TestClient(create_app()) as client:
            who = athlete_with_files(client, "Clean")
            ref = pay(who)
            client.post(review_url(request_id_of(who)) + "/approve", headers=reviewer(LGA).headers)

        from kafriada.contexts.access import service as access
        from kafriada.contexts.ledger import reversal
        from tests._access_helpers import make_user

        admin_id, _ = make_user("Admin", password="a long test passphrase", grants=[("super_admin", "global", None)])
        principal = access.authenticate(access.issue_session(admin_id, method="test").token)
        assert principal is not None
        reversal.record_reversal(principal, ref, 100_000, "Customer refunded in the dashboard.", "a long test passphrase")

        mine_ids = [str(r["id"]) for r in sql(
            "SELECT m.id FROM identity.media_files m JOIN identity.athletes a ON a.id = m.athlete_id "
            "WHERE a.user_id = :u", u=who.user_id)]
        media = [f for f in integrity.check_media(LocalStore(tmp_path)) if any(i in f.detail for i in mine_ids)]
        assert media == []
        # The whole shared database — every payment, athlete and request the suite has ever
        # made — adds up too. (Media is left out of the whole-database sweep: the objects of
        # earlier tests lived in temporary folders that no longer exist.)
        everything = integrity.check_ledger() + integrity.check_identity() + integrity.check_verification()
        assert [f"{f.check}: {f.detail}" for f in everything] == []


class TestLedgerFindings:
    def test_a_settled_payment_with_no_lines_is_reported_with_everything_missing(
        self, scratch: Session, payer: Athlete
    ) -> None:
        ref = payment(scratch, payer, "success")
        found = checks(scratch, only=ref)
        assert any(f.startswith("ledger.settled_payment_shape") for f in found)
        assert any(f.startswith("ledger.settled_without_a_delivery_record") for f in found)
        assert any(f.startswith("ledger.settled_payment_without_audit") for f in found)

    def test_a_gross_that_is_not_the_price_agreed_is_reported(self, scratch: Session, payer: Athlete) -> None:
        ref = payment(scratch, payer, "success")
        line(scratch, ref, "credit", "paystack", 1_000)
        line(scratch, ref, "debit", "fee", 15)
        delivered_and_audited(scratch, ref)
        (finding,) = [f for f in checks(scratch, only=ref)]
        assert "gross 1000 vs agreed 250000" in finding

    def test_a_fee_that_swallows_the_payment_is_reported(self, scratch: Session, payer: Athlete) -> None:
        ref = payment(scratch, payer, "success")
        line(scratch, ref, "credit", "paystack", 250_000)
        line(scratch, ref, "debit", "fee", 250_000)
        delivered_and_audited(scratch, ref)
        assert any("fee 250000" in f for f in checks(scratch, only=ref))

    def test_a_missing_fee_line_is_reported(self, scratch: Session, payer: Athlete) -> None:
        ref = payment(scratch, payer, "success")
        line(scratch, ref, "credit", "paystack", 250_000)
        delivered_and_audited(scratch, ref)
        assert any("fee lines 0" in f for f in checks(scratch, only=ref))

    def test_a_refund_larger_than_the_payment_is_reported(self, scratch: Session, payer: Athlete) -> None:
        ref = payment(scratch, payer, "success")
        line(scratch, ref, "credit", "paystack", 250_000)
        line(scratch, ref, "debit", "fee", 3_750)
        line(scratch, ref, "debit", "reversal", 250_001, note="typed too many zeros", by=payer.user_id)
        delivered_and_audited(scratch, ref)
        assert any("reversed 250001" in f for f in checks(scratch, only=ref))

    def test_a_correct_settlement_with_a_refund_is_not_reported(self, scratch: Session, payer: Athlete) -> None:
        ref = payment(scratch, payer, "success")
        line(scratch, ref, "credit", "paystack", 250_000)
        line(scratch, ref, "debit", "fee", 3_750)
        line(scratch, ref, "debit", "reversal", 100_000, note="refunded", by=payer.user_id)
        delivered_and_audited(scratch, ref)
        assert checks(scratch, only=ref) == []

    @pytest.mark.parametrize("status", ["pending", "failed", "abandoned", "frozen"])
    def test_a_ledger_line_on_a_payment_that_never_settled_is_reported(
        self, scratch: Session, payer: Athlete, status: str
    ) -> None:
        ref = payment(scratch, payer, status)
        line(scratch, ref, "credit", "paystack", 250_000)
        found = checks(scratch, only=ref)
        assert any(f.startswith("ledger.line_on_unsettled_payment") and status in f for f in found)


class TestIdentityFindings:
    def test_a_counter_behind_the_serials_in_use_is_reported(self, scratch: Session, payer: Athlete) -> None:
        scratch.execute(text("UPDATE identity.kuid_counters SET next_serial = next_serial - 1 "
                             "WHERE state_code = 'JG'"))
        assert any(f.startswith("identity.serial_counter_behind") for f in checks(scratch))

    def test_a_counter_ahead_of_the_athletes_issued_is_a_reported_gap(self, scratch: Session) -> None:
        scratch.execute(text("UPDATE identity.kuid_counters SET next_serial = next_serial + 1 "
                             "WHERE state_code = 'JG'"))
        assert any(f.startswith("identity.serial_gap") for f in checks(scratch))

    def test_athletes_with_no_counter_at_all_are_reported(self, scratch: Session) -> None:
        scratch.execute(text("DELETE FROM identity.kuid_counters WHERE state_code = 'JG'"))
        assert any(f.startswith("identity.athlete_without_a_counter") for f in checks(scratch))


class TestVerificationFindings:
    def test_a_review_whose_payment_is_not_settled_is_reported(
        self, scratch: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_local_store(monkeypatch, tmp_path)
        with TestClient(create_app()) as client:
            who = athlete_with_files(client, "Unpaid review")
        ref = payment(scratch, who)  # pending
        scratch.execute(
            text("UPDATE identity.verification_requests v SET status = 'under_review', "
                 "payment_id = (SELECT id FROM money.payments WHERE reference = :r) WHERE v.id = :id"),
            {"r": ref, "id": request_id_of(who)},
        )
        assert any(f.startswith("verification.reviewed_without_settled_payment") and "under_review" in f
                   for f in checks(scratch))

    def test_an_approval_with_no_decision_on_record_is_reported(
        self, scratch: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_local_store(monkeypatch, tmp_path)
        with TestClient(create_app()) as client:
            who = athlete_with_files(client, "Silent approval")
            pay(who)
        scratch.execute(text("UPDATE identity.verification_requests SET status = 'approved' WHERE id = :id"),
                        {"id": request_id_of(who)})
        found = checks(scratch, only=str(request_id_of(who)))
        assert any(f.startswith("verification.decision_missing") for f in found)

    def test_an_approval_whose_photo_is_not_ready_is_reported(
        self, scratch: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        use_local_store(monkeypatch, tmp_path)
        with TestClient(create_app()) as client:
            who = athlete_with_files(client, "Photo gone")
            pay(who)
        scratch.execute(text("UPDATE identity.verification_requests SET status = 'approved' WHERE id = :id"),
                        {"id": request_id_of(who)})
        scratch.execute(text("UPDATE identity.media_files SET status = 'deleted' WHERE id = "
                             "(SELECT photo_media_id FROM identity.verification_requests WHERE id = :id)"),
                        {"id": request_id_of(who)})
        found = checks(scratch, only=str(request_id_of(who)))
        assert any(f.startswith("verification.approved_without_files") for f in found)


class TestMediaFindings:
    def test_a_ready_file_whose_object_has_gone_missing_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = use_local_store(monkeypatch, tmp_path)
        with TestClient(create_app()) as client:
            who = athlete_with_files(client, "Missing object")
        (row,) = sql(
            "SELECT m.id::text AS id, m.derivative_key FROM identity.media_files m "
            "JOIN identity.athletes a ON a.id = m.athlete_id WHERE a.user_id = :u AND m.kind = 'photo'",
            u=who.user_id,
        )
        def mine() -> list[integrity.Finding]:
            return [f for f in integrity.check_media(store) if str(row["id"]) in f.detail]

        assert mine() == []
        store.delete(str(row["derivative_key"]))
        found = mine()
        assert [f.check for f in found] == ["media.object_missing"]

    def test_an_unreachable_store_is_reported_not_swallowed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from kafriada.contexts.media.store import StoreError

        store = use_local_store(monkeypatch, tmp_path)
        with TestClient(create_app()) as client:
            athlete_with_files(client, "Store down")

        def down(key: str):  # type: ignore[no-untyped-def]
            raise StoreError("r2 unreachable: ConnectTimeout")

        monkeypatch.setattr(store, "head", down)
        found = integrity.check_media(store)
        assert [f.check for f in found] == ["media.store_unreachable"]  # and it stops, having said so

    def test_no_store_configured_is_not_a_finding(self) -> None:
        from kafriada.contexts.media.store import NoStore

        assert integrity.check_media(NoStore()) == []


def test_the_scratch_session_really_does_leave_nothing_behind(payer: Athlete) -> None:
    ref = new_reference()
    session = Session(bind=money_engine(), future=True)
    session.execute(text("INSERT INTO money.payments (reference, purpose, expected_kobo, paid_by) "
                         "VALUES (:r, 'stage2_athlete', 250000, :u)"), {"r": ref, "u": payer.user_id})
    session.rollback()
    session.close()
    assert sql("SELECT 1 FROM money.payments WHERE reference = :r", r=ref) == []
    assert uuid4()  # keep the import honest

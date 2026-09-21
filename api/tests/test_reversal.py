"""Recording a refund made by hand in the Paystack dashboard (ADM-04).

What is proved here:
  - a super administrator can RECORD a refund — password re-entered, reason mandatory —
    as one debit line against the settled payment, kept with who and why, with an audit row
  - it is refused for an unsettled payment, a second time, more than was paid, no amount,
    no reason, or a wrong password — and each refusal writes nothing
  - nobody else can: not a coordinator, not an athlete, not anonymous
  - it cannot MOVE money: no call goes to Paystack, and nothing else about the payment,
    the athlete or the verification changes
  - the database itself refuses a reversal with no author or no reason, and a reversal
    line can no more be edited or deleted than any other ledger line
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from kafriada.contexts.ledger.entries import InvalidAmount, plan_reversal
from kafriada.main import create_app
from tests._access_helpers import sql
from tests._media_helpers import LGA, pay, reviewer, super_admin
from tests._payment_helpers import Athlete, new_athlete, pending_payment, state

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not (os.environ.get("DATABASE_URL_APP") and os.environ.get("DATABASE_URL_MONEY")
             and os.environ.get("DATABASE_URL_MIGRATE")),
        reason="needs the app, money and migrate database URLs",
    ),
]

PASSWORD = "a long test passphrase"
GROSS = 250_000


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def admin() -> Athlete:
    return super_admin(PASSWORD)


def url(ref: str) -> str:
    return f"/v1/admin/payments/{ref}/reversal"


def body(**over: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "amount_kobo": 100_000,
        "reason": "Refunded in the Paystack dashboard after a duplicate charge.",
        "current_password": PASSWORD,
    }
    fields.update(over)
    return fields


def settled(name: str = "Refund") -> tuple[Athlete, str]:
    who = new_athlete(name)
    return who, pay(who)


def reversal_lines(ref: str) -> list[dict[str, object]]:
    return sql(
        "SELECT l.direction, l.amount_kobo, l.note, l.recorded_by FROM money.ledger_entries l "
        "JOIN money.payments p ON p.id = l.payment_id WHERE p.reference = :r AND l.source = 'reversal'",
        r=ref,
    )


class TestRecording:
    def test_a_partial_refund_is_recorded_with_who_and_why_and_audited(
        self, client: TestClient, admin: Athlete
    ) -> None:
        _, ref = settled()
        done = client.post(url(ref), json=body(), headers=admin.headers)

        assert done.status_code == 201, done.text
        assert done.json() == {"reference": ref, "amount_kobo": 100_000, "gross_kobo": GROSS}
        (line,) = reversal_lines(ref)
        assert line["direction"] == "debit" and line["amount_kobo"] == 100_000
        assert line["note"] == "Refunded in the Paystack dashboard after a duplicate charge."
        assert line["recorded_by"] == admin.user_id
        audit = sql(
            "SELECT action, metadata FROM ops.audit_log WHERE subject_type = 'payment' "
            "AND subject_id = (SELECT id::text FROM money.payments WHERE reference = :r) "
            "AND action = 'payment.reversal_recorded'", r=ref)
        assert len(audit) == 1 and audit[0]["metadata"]["amount_kobo"] == 100_000  # type: ignore[index]

    def test_a_full_refund_is_allowed_and_the_two_original_lines_are_untouched(
        self, client: TestClient, admin: Athlete
    ) -> None:
        _, ref = settled()
        assert client.post(url(ref), json=body(amount_kobo=GROSS), headers=admin.headers).status_code == 201
        assert state(ref)["ledger"] == [
            ("debit", "fee", 3_750), ("credit", "paystack", GROSS), ("debit", "reversal", GROSS),
        ]

    def test_it_changes_nothing_else_about_the_payment_or_the_persons_verification(
        self, client: TestClient, admin: Athlete
    ) -> None:
        _, ref = settled()
        before = sql("SELECT status FROM money.payments WHERE reference = :r", r=ref)
        client.post(url(ref), json=body(), headers=admin.headers)
        assert sql("SELECT status FROM money.payments WHERE reference = :r", r=ref) == before
        assert state(ref)["status"] == "success"

    def test_no_call_can_reach_paystack_because_none_is_made(
        self, client: TestClient, admin: Athlete, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, ref = settled()

        def forbidden(*a: object, **k: object) -> httpx.Response:
            raise AssertionError("recording a refund must never contact the payment provider")

        for name in ("request", "get", "post", "put", "delete", "patch"):
            monkeypatch.setattr(httpx, name, forbidden)
        assert client.post(url(ref), json=body(), headers=admin.headers).status_code == 201


class TestRefusals:
    def _nothing_written(self, ref: str) -> None:
        assert reversal_lines(ref) == []

    def test_a_pending_payment_has_nothing_to_refund(self, client: TestClient, admin: Athlete) -> None:
        ref = pending_payment(new_athlete("Pending"))
        refused = client.post(url(ref), json=body(), headers=admin.headers)
        assert refused.status_code == 409 and "settled" in refused.text
        self._nothing_written(ref)

    def test_a_second_refund_on_the_same_payment_is_refused(self, client: TestClient, admin: Athlete) -> None:
        _, ref = settled()
        assert client.post(url(ref), json=body(), headers=admin.headers).status_code == 201
        again = client.post(url(ref), json=body(amount_kobo=1_000), headers=admin.headers)
        assert again.status_code == 409 and "already recorded" in again.text
        assert len(reversal_lines(ref)) == 1

    @pytest.mark.parametrize("amount", [GROSS + 1, 0, -5])
    def test_an_amount_that_cannot_be_a_refund_is_refused(
        self, client: TestClient, admin: Athlete, amount: int
    ) -> None:
        _, ref = settled()
        refused = client.post(url(ref), json=body(amount_kobo=amount), headers=admin.headers)
        assert refused.status_code == 422
        self._nothing_written(ref)

    @pytest.mark.parametrize("amount", ["100000", 1000.5, True, None])
    def test_an_amount_that_is_not_a_whole_number_of_kobo_is_refused(
        self, client: TestClient, admin: Athlete, amount: object
    ) -> None:
        _, ref = settled()
        refused = client.post(url(ref), json=body(amount_kobo=amount), headers=admin.headers)
        assert refused.status_code == 422
        self._nothing_written(ref)

    @pytest.mark.parametrize("reason", ["", "   ", None])
    def test_a_reason_is_mandatory(self, client: TestClient, admin: Athlete, reason: object) -> None:
        _, ref = settled()
        assert client.post(url(ref), json=body(reason=reason), headers=admin.headers).status_code == 422
        self._nothing_written(ref)

    def test_the_password_must_be_entered_again_and_be_right(self, client: TestClient, admin: Athlete) -> None:
        _, ref = settled()
        wrong = client.post(url(ref), json=body(current_password="not the password!!"), headers=admin.headers)
        missing = client.post(url(ref), json={"amount_kobo": 1, "reason": "x"}, headers=admin.headers)
        assert wrong.status_code == 422 and missing.status_code == 422
        assert wrong.json()["error"]["message"]["field"] == "current_password"
        self._nothing_written(ref)

    def test_an_unknown_reference_is_a_404(self, client: TestClient, admin: Athlete) -> None:
        ref = "KAF-00000000-0000-4000-8000-000000000000"
        assert client.post(url(ref), json=body(), headers=admin.headers).status_code == 404

    def test_only_a_super_administrator_may_record_one(self, client: TestClient, admin: Athlete) -> None:
        who, ref = settled()
        for headers in (
            {},  # anonymous
            who.headers,  # the athlete who paid
            reviewer(LGA).headers,  # a coordinator, whose job is verification not money
        ):
            refused = client.post(url(ref), json=body(), headers=headers)
            assert refused.status_code in (401, 403)
        self._nothing_written(ref)


class TestTheDatabaseHoldsTheLine:
    def _engine(self, name: str):  # type: ignore[no-untyped-def]
        return create_engine(os.environ[f"DATABASE_URL_{name}"], future=True)

    def _payment_id(self, ref: str) -> object:
        return sql("SELECT id FROM money.payments WHERE reference = :r", r=ref)[0]["id"]

    def test_a_reversal_with_no_author_or_no_reason_cannot_exist(self, client: TestClient) -> None:
        _, ref = settled()
        pid = self._payment_id(ref)
        insert = ("INSERT INTO money.ledger_entries (payment_id, direction, source, amount_kobo, note, recorded_by) "
                  "VALUES (:p, 'debit', 'reversal', 100, :note, :by)")
        author = sql("SELECT id FROM ops.users LIMIT 1")[0]["id"]
        for note, by in ((None, author), ("   ", author), ("a reason", None)):
            with pytest.raises(IntegrityError), self._engine("MONEY").begin() as conn:
                conn.execute(text(insert), {"p": pid, "note": note, "by": by})
        assert reversal_lines(ref) == []

    def test_a_reversal_cannot_be_a_credit_or_a_zero(self, client: TestClient) -> None:
        _, ref = settled()
        pid = self._payment_id(ref)
        author = sql("SELECT id FROM ops.users LIMIT 1")[0]["id"]
        for direction, amount in (("credit", 100), ("debit", 0)):
            with pytest.raises(IntegrityError), self._engine("MONEY").begin() as conn:
                conn.execute(
                    text("INSERT INTO money.ledger_entries (payment_id, direction, source, amount_kobo, note, recorded_by) "
                         "VALUES (:p, :d, 'reversal', :a, 'because', :by)"),
                    {"p": pid, "d": direction, "a": amount, "by": author},
                )

    def test_a_reversal_line_is_as_permanent_as_any_other(self, client: TestClient, admin: Athlete) -> None:
        _, ref = settled()
        client.post(url(ref), json=body(), headers=admin.headers)
        for role in ("MONEY", "MIGRATE"):
            for statement in (
                "UPDATE money.ledger_entries SET amount_kobo = 1 WHERE source = 'reversal' AND payment_id = :p",
                "DELETE FROM money.ledger_entries WHERE source = 'reversal' AND payment_id = :p",
            ):
                with pytest.raises(DBAPIError) as caught, self._engine(role).begin() as conn:
                    conn.execute(text(statement), {"p": self._payment_id(ref)})
                assert "permission denied" in str(caught.value) or "append-only" in str(caught.value)
        assert len(reversal_lines(ref)) == 1


class TestPlanning:
    def test_a_reversal_is_one_debit_for_the_amount_refunded(self) -> None:
        line = plan_reversal(gross_kobo=GROSS, amount_kobo=100)
        assert (line.direction.value, line.source.value, line.amount_kobo) == ("debit", "reversal", 100)

    @pytest.mark.parametrize(("gross", "amount"), [(GROSS, GROSS + 1), (GROSS, 0), (GROSS, -1), (0, 1), (-5, 1)])
    def test_impossible_amounts_are_refused(self, gross: int, amount: int) -> None:
        with pytest.raises(InvalidAmount):
            plan_reversal(gross_kobo=gross, amount_kobo=amount)

    @pytest.mark.parametrize("amount", [True, 10.5, "10", None])
    def test_only_whole_kobo_are_money(self, amount: object) -> None:
        with pytest.raises(InvalidAmount):
            plan_reversal(gross_kobo=GROSS, amount_kobo=amount)  # type: ignore[arg-type]

    def test_a_refund_of_exactly_the_payment_is_allowed(self) -> None:
        assert plan_reversal(gross_kobo=GROSS, amount_kobo=GROSS).amount_kobo == GROSS

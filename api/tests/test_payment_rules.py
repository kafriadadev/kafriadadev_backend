"""Tests for the payment rules — what a Paystack event is allowed to do.

These run without a database, a network or a Paystack account. That is the point
of keeping the rules pure: the cases that matter most here (a ten-naira payment
buying a 2,500-naira badge, a currency that is not naira, a fee that is not
credible) are exactly the ones that are hard to arrange against a real gateway and
trivial to arrange as a dictionary.

What these do *not* cover, on purpose: replayed webhooks. "Five copies of one
webhook produce exactly two ledger rows" is a property of a database insert, not
of these rules, and is tested against the database in the settlement service.
"""

from __future__ import annotations

import itertools

import pytest

from kafriada.contexts.ledger.entries import plan_settlement
from kafriada.contexts.payments.rules import (
    ChargeEvent,
    IllegalTransition,
    MalformedEvent,
    PaymentStatus,
    Purpose,
    Verdict,
    decide,
    expected_amount_kobo,
    is_our_reference,
    new_reference,
    parse_charge_event,
    transition,
)
from kafriada.settings import Settings

ATHLETE_PRICE = 250_000  # 2,500 naira
CLUB_PRICE = 1_500_000  # 15,000 naira


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url_app": "postgresql+psycopg://kaf_app:pw@localhost:5432/kafriada",
        "database_url_money": "postgresql+psycopg://kaf_money:pw@localhost:5432/kafriada",
        "secret_key": "x" * 40,
        "qr_secret": "y" * 40,
    }
    base.update(overrides)
    # Tests must not read the developer's local .env — see the note in
    # test_settings_refuses_insecure_config.
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def _event(**overrides: object) -> ChargeEvent:
    fields: dict[str, object] = {
        "reference": new_reference(),
        "amount_kobo": ATHLETE_PRICE,
        "currency": "NGN",
        "status": "success",
        "fees_kobo": 3_750,
    }
    fields.update(overrides)
    return ChargeEvent(**fields)  # type: ignore[arg-type]


def _payload(**data: object) -> dict[str, object]:
    body: dict[str, object] = {
        "reference": new_reference(),
        "amount": ATHLETE_PRICE,
        "currency": "NGN",
        "status": "success",
        "fees": 3_750,
    }
    body.update(data)
    return {"event": "charge.success", "data": body}


# ---------------------------------------------------------------------------
# Prices come from configuration
# ---------------------------------------------------------------------------
class TestPrices:

    def test_the_two_prices_are_the_ones_in_the_specification(self) -> None:
        settings = _settings()
        assert expected_amount_kobo(Purpose.STAGE2_ATHLETE, settings) == ATHLETE_PRICE
        assert expected_amount_kobo(Purpose.STAGE2_ORG, settings) == CLUB_PRICE

    def test_a_price_change_is_configuration_not_code(self) -> None:
        settings = _settings(price_athlete_verification_kobo=300_000)
        assert expected_amount_kobo(Purpose.STAGE2_ATHLETE, settings) == 300_000
        # ...and only the price it was asked about moves.
        assert expected_amount_kobo(Purpose.STAGE2_ORG, settings) == CLUB_PRICE


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------
class TestReferences:

    def test_a_new_reference_is_recognised_as_ours(self) -> None:
        assert is_our_reference(new_reference())

    def test_references_do_not_collide(self) -> None:
        assert len({new_reference() for _ in range(2_000)}) == 2_000

    @pytest.mark.parametrize(
        "reference",
        [
            "",
            "KAF-",
            "KAF-123",
            "T123456789",  # a plain Paystack reference from some other product
            "kaf-" + "0" * 8 + "-0000-0000-0000-" + "0" * 12,  # wrong case on the prefix
            "KAF-" + "A" * 8 + "-0000-0000-0000-" + "0" * 12,  # uppercase hex
            "XKAF-" + "0" * 8 + "-0000-0000-0000-" + "0" * 12,  # something in front
        ],
    )
    def test_anything_else_is_not_ours(self, reference: str) -> None:
        assert not is_our_reference(reference)

    def test_a_trailing_newline_is_not_ours(self) -> None:
        """The classic ``re.match(...$)`` hole: ``$`` also matches before a final
        newline, so a reference with one appended would pass a careless check."""
        assert not is_our_reference(new_reference() + "\n")


# ---------------------------------------------------------------------------
# Reading the event
# ---------------------------------------------------------------------------
class TestParsing:

    def test_a_good_charge_is_read_field_for_field(self) -> None:
        payload = _payload(reference="KAF-abc", amount=250_000, fees=3_750)
        event = parse_charge_event(payload)
        assert event == ChargeEvent("KAF-abc", 250_000, "NGN", "success", 3_750)

    @pytest.mark.parametrize(
        "event_name", ["transfer.success", "refund.processed", "subscription.create", "", None]
    )
    def test_other_events_are_not_our_business(self, event_name: object) -> None:
        assert parse_charge_event({"event": event_name, "data": {"amount": "garbage"}}) is None

    def test_a_missing_event_name_is_not_our_business(self) -> None:
        assert parse_charge_event({"data": {}}) is None

    @pytest.mark.parametrize("body", [[], "charge.success", None, 42, [{"event": "charge.success"}]])
    def test_a_body_that_is_not_an_object_is_malformed(self, body: object) -> None:
        with pytest.raises(MalformedEvent):
            parse_charge_event(body)

    def test_charge_success_without_data_is_malformed(self) -> None:
        with pytest.raises(MalformedEvent):
            parse_charge_event({"event": "charge.success"})
        with pytest.raises(MalformedEvent):
            parse_charge_event({"event": "charge.success", "data": "nope"})

    @pytest.mark.parametrize("amount", [250_000.0, 250_000.5, "250000", None, True, [250_000]])
    def test_an_amount_that_is_not_whole_kobo_is_malformed(self, amount: object) -> None:
        """Floats and strings are refused, and so is ``True`` — a bool is an int in
        Python and would otherwise read as one kobo."""
        with pytest.raises(MalformedEvent, match="amount"):
            parse_charge_event(_payload(amount=amount))

    @pytest.mark.parametrize("field", ["reference", "currency", "status"])
    @pytest.mark.parametrize("value", ["", None, 7, ["x"]])
    def test_a_text_field_that_is_not_text_is_malformed(self, field: str, value: object) -> None:
        with pytest.raises(MalformedEvent, match=field):
            parse_charge_event(_payload(**{field: value}))

    def test_a_missing_field_is_malformed_not_defaulted(self) -> None:
        body = _payload()
        del body["data"]["amount"]  # type: ignore[attr-defined]
        with pytest.raises(MalformedEvent, match="amount"):
            parse_charge_event(body)

    def test_a_missing_fee_is_kept_as_missing_not_zero(self) -> None:
        """A made-up zero in a ledger looks right and is wrong; ``None`` is loud."""
        event = parse_charge_event(_payload(fees=None))
        assert event is not None
        assert event.fees_kobo is None

    @pytest.mark.parametrize("fees", [37.5, "3750", True])
    def test_a_fee_that_is_not_whole_kobo_is_malformed(self, fees: object) -> None:
        with pytest.raises(MalformedEvent, match="fees"):
            parse_charge_event(_payload(fees=fees))


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------
class TestDecision:

    def test_the_exact_amount_settles(self) -> None:
        assert decide(_event(), expected_kobo=ATHLETE_PRICE).verdict is Verdict.SETTLE

    def test_a_ten_naira_payment_cannot_buy_a_2500_naira_badge(self) -> None:
        """The reason this module exists. The amount is compared with the price
        *we* hold, not with anything the payment claims about itself."""
        decision = decide(_event(amount_kobo=1_000), expected_kobo=ATHLETE_PRICE)
        assert decision.verdict is Verdict.FREEZE
        assert "1000" in decision.reason
        assert str(ATHLETE_PRICE) in decision.reason

    def test_an_athlete_payment_cannot_buy_a_club_badge(self) -> None:
        """Right currency, right status, a perfectly good payment — for the wrong
        product. Cheaper by 1,250,000 kobo, and must not approve."""
        decision = decide(_event(amount_kobo=ATHLETE_PRICE), expected_kobo=CLUB_PRICE)
        assert decision.verdict is Verdict.FREEZE

    @pytest.mark.parametrize("delta", [-250_000, -1_000, -1, 1, 1_000, 250_000])
    def test_any_difference_at_all_freezes_including_overpayment(self, delta: int) -> None:
        event = _event(amount_kobo=ATHLETE_PRICE + delta)
        assert decide(event, expected_kobo=ATHLETE_PRICE).verdict is Verdict.FREEZE

    def test_only_the_exact_amount_settles_across_a_sweep(self) -> None:
        settled = [
            amount
            for amount in range(ATHLETE_PRICE - 50, ATHLETE_PRICE + 51)
            if decide(_event(amount_kobo=amount), expected_kobo=ATHLETE_PRICE).verdict
            is Verdict.SETTLE
        ]
        assert settled == [ATHLETE_PRICE]

    @pytest.mark.parametrize("currency", ["USD", "GHS", "ngn", "NGN ", ""])
    def test_a_currency_that_is_not_naira_freezes_even_at_the_right_number(
        self, currency: str
    ) -> None:
        decision = decide(_event(currency=currency), expected_kobo=ATHLETE_PRICE)
        assert decision.verdict is Verdict.FREEZE
        assert "currency" in decision.reason

    @pytest.mark.parametrize("status", ["failed", "abandoned", "pending", "SUCCESS", ""])
    def test_a_status_that_is_not_success_freezes(self, status: str) -> None:
        decision = decide(_event(status=status), expected_kobo=ATHLETE_PRICE)
        assert decision.verdict is Verdict.FREEZE
        assert "status" in decision.reason

    def test_a_missing_fee_freezes_rather_than_being_guessed(self) -> None:
        decision = decide(_event(fees_kobo=None), expected_kobo=ATHLETE_PRICE)
        assert decision.verdict is Verdict.FREEZE
        assert "fee" in decision.reason

    @pytest.mark.parametrize("fee", [-1, ATHLETE_PRICE, ATHLETE_PRICE + 1, 250_000_000])
    def test_a_fee_that_is_not_credible_freezes(self, fee: int) -> None:
        assert decide(_event(fees_kobo=fee), expected_kobo=ATHLETE_PRICE).verdict is Verdict.FREEZE

    def test_a_waived_fee_of_zero_still_settles(self) -> None:
        assert decide(_event(fees_kobo=0), expected_kobo=ATHLETE_PRICE).verdict is Verdict.SETTLE

    def test_every_settle_is_something_the_ledger_can_write(self) -> None:
        """The promise in :func:`decide`'s docstring, checked over a grid: a SETTLE
        verdict means the ledger planner will not then refuse the same figures
        halfway through the transaction that is supposed to record them."""
        fees = [-5, -1, 0, 1, 3_750, ATHLETE_PRICE - 1, ATHLETE_PRICE, ATHLETE_PRICE + 1, None]
        currencies = ["NGN", "USD"]
        statuses = ["success", "failed"]
        amounts = [1_000, ATHLETE_PRICE - 1, ATHLETE_PRICE, ATHLETE_PRICE + 1]

        settled = 0
        for amount, fee, currency, status in itertools.product(amounts, fees, currencies, statuses):
            event = _event(amount_kobo=amount, fees_kobo=fee, currency=currency, status=status)
            if decide(event, expected_kobo=ATHLETE_PRICE).verdict is Verdict.SETTLE:
                settled += 1
                assert event.fees_kobo is not None
                plan_settlement(gross_kobo=event.amount_kobo, provider_fee_kobo=event.fees_kobo)
        # Guard against the loop passing by never settling anything. Exactly four
        # combinations qualify: NGN, success, the exact amount, and a credible fee
        # (0, 1, 3_750 or ATHLETE_PRICE - 1) — the negative, equal, larger and
        # missing fees in the grid must all have been refused.
        assert settled == 4

    def test_the_reason_never_claims_a_settle_it_did_not_make(self) -> None:
        for event in (_event(amount_kobo=1), _event(currency="USD"), _event(fees_kobo=None)):
            decision = decide(event, expected_kobo=ATHLETE_PRICE)
            assert decision.verdict is Verdict.FREEZE
            assert decision.reason


# ---------------------------------------------------------------------------
# A payment's life
# ---------------------------------------------------------------------------
S = PaymentStatus

# Written out by hand rather than read back from the implementation, so this is a
# check against the specification and not a copy of the code. Anything not listed
# here must be refused — 25 pairs, every one asserted below.
LEGAL = {
    (S.PENDING, S.SUCCESS),
    (S.PENDING, S.FAILED),
    (S.PENDING, S.ABANDONED),
    (S.PENDING, S.FROZEN),
    # A confirmed payment beats expiry, and a retry on the same reference beats a
    # failed attempt: real money arriving late is a success, not an error.
    (S.ABANDONED, S.SUCCESS),
    (S.FAILED, S.SUCCESS),
    # ...and if that late money is the wrong amount, it freezes rather than vanishing.
    (S.ABANDONED, S.FROZEN),
    (S.FAILED, S.FROZEN),
}


class TestPaymentStatus:

    @pytest.mark.parametrize(
        ("current", "target"), list(itertools.product(PaymentStatus, PaymentStatus))
    )
    def test_every_pair_is_legal_only_if_the_specification_says_so(
        self, current: PaymentStatus, target: PaymentStatus
    ) -> None:
        if (current, target) in LEGAL:
            assert transition(current, target) is target
        else:
            with pytest.raises(IllegalTransition):
                transition(current, target)

    def test_a_settled_payment_is_final(self) -> None:
        for target in PaymentStatus:
            with pytest.raises(IllegalTransition):
                transition(S.SUCCESS, target)

    def test_code_cannot_unfreeze_money(self) -> None:
        for target in PaymentStatus:
            with pytest.raises(IllegalTransition):
                transition(S.FROZEN, target)

    def test_the_error_says_what_was_attempted(self) -> None:
        with pytest.raises(IllegalTransition, match="success payment cannot become failed"):
            transition(S.SUCCESS, S.FAILED)

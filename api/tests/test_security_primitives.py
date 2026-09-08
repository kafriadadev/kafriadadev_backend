"""Tests for the security primitives.

These run without a database. They exist because every one of them corresponds to
a way the system could be wrong in a manner nobody would notice by using it: a
password that verifies when it should not, a signature that accepts a forgery, a
timing difference that reveals which phone numbers are registered.
"""

from __future__ import annotations

import time

import pytest

from kafriada.security.passwords import (
    MIN_PASSWORD_LENGTH,
    PasswordService,
    PasswordTooLongError,
    password_policy_error,
)
from kafriada.security.signing import QrSigner, verify_paystack_signature
from kafriada.security.tokens import (
    fingerprint_request,
    hash_otp,
    hash_token,
    new_otp,
    new_token,
    tokens_equal,
)
from kafriada.settings import Settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url_app": "postgresql+psycopg://kaf_app:pw@localhost:5432/kafriada",
        "database_url_money": "postgresql+psycopg://kaf_money:pw@localhost:5432/kafriada",
        "secret_key": "x" * 40,
        "qr_secret": "y" * 40,
        # Fast hashing so the suite stays quick. Production values come from the
        # environment and are floored at the OWASP minimum by the field validator.
        "argon2_memory_kib": 19_456,
        "argon2_time_cost": 2,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def service() -> PasswordService:
    """Built once for the module — constructing it computes the timing hash."""
    return PasswordService(_settings())


class TestPasswords:

    def test_hash_is_argon2id_and_salted(self, service: PasswordService) -> None:
        first = service.hash("correct horse battery staple")
        second = service.hash("correct horse battery staple")
        assert first.startswith("$argon2id$")
        # Two hashes of the same password must differ, or the salt is not doing
        # its job and identical passwords become visible across accounts.
        assert first != second

    def test_correct_password_verifies(self, service: PasswordService) -> None:
        stored = service.hash("a-real-password-here")
        assert service.verify(stored, "a-real-password-here").ok is True

    def test_wrong_password_returns_false_and_does_not_raise(
        self, service: PasswordService
    ) -> None:
        stored = service.hash("a-real-password-here")
        result = service.verify(stored, "not-the-password")
        assert result.ok is False

    def test_malformed_stored_hash_is_false_not_an_exception(
        self, service: PasswordService
    ) -> None:
        # A corrupted or truncated hash column must fail closed. If this raised,
        # a caller catching broadly could treat the error as success.
        assert service.verify("not-a-hash", "anything").ok is False
        assert service.verify("", "anything").ok is False

    def test_oversized_password_is_rejected_before_hashing(
        self, service: PasswordService
    ) -> None:
        # Argon2 reads the whole input, so an unbounded password is a way to burn
        # CPU on a box with two cores.
        with pytest.raises(PasswordTooLongError):
            service.hash("a" * 2000)
        assert service.verify("$argon2id$fake", "a" * 2000).ok is False

    def test_dummy_verify_costs_about_the_same_as_a_real_one(
        self, service: PasswordService
    ) -> None:
        """Unknown-user sign-in must not be measurably faster than known-user.

        Otherwise response timing becomes an oracle for which phone numbers are
        registered — which, for a register of athletes, is itself personal data.
        """
        stored = service.hash("timing-comparison-password")

        start = time.perf_counter()
        service.verify(stored, "wrong-password-entirely")
        real = time.perf_counter() - start

        start = time.perf_counter()
        service.verify_dummy()
        dummy = time.perf_counter() - start

        # Generous bound: this is a smoke test against someone replacing
        # verify_dummy with `pass`, not a statistical timing analysis.
        assert dummy > real * 0.25, "dummy verification is suspiciously cheap"

    @pytest.mark.parametrize(
        "candidate",
        ["", "short", "a" * (MIN_PASSWORD_LENGTH - 1)],
    )
    def test_policy_rejects_short_passwords(self, candidate: str) -> None:
        assert password_policy_error(candidate) is not None

    def test_policy_accepts_a_long_passphrase_without_composition_rules(self) -> None:
        # NIST guidance: length beats forced complexity. Composition rules push
        # people towards predictable substitutions and sticky notes.
        assert password_policy_error("all lowercase words no symbols at all") is None


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
class TestTokens:
    def test_tokens_are_unique_and_long(self) -> None:
        tokens = {new_token() for _ in range(500)}
        assert len(tokens) == 500
        assert all(len(t) >= 40 for t in tokens)

    def test_hash_is_deterministic_and_not_reversible_to_the_token(self) -> None:
        raw = new_token()
        assert hash_token(raw) == hash_token(raw)
        assert raw not in hash_token(raw)
        assert len(hash_token(raw)) == 64

    def test_constant_time_compare_matches_equality(self) -> None:
        assert tokens_equal("abc", "abc") is True
        assert tokens_equal("abc", "abd") is False
        assert tokens_equal("abc", "ab") is False

    def test_otp_is_six_digits_and_zero_padded(self) -> None:
        codes = [new_otp() for _ in range(200)]
        assert all(len(c) == 6 and c.isdigit() for c in codes)
        # Uniformly random over the full range, so leading zeros must occur.
        assert len(set(codes)) > 150

    def test_otp_hash_is_keyed_so_a_stolen_table_is_not_a_lookup_table(self) -> None:
        # Six digits is a million possibilities. An unkeyed digest of that is
        # reversible in seconds, so the pepper is what makes storage safe.
        assert hash_otp("123456", pepper="pepper-a") != hash_otp("123456", pepper="pepper-b")
        assert hash_otp("123456", pepper="p") == hash_otp("123456", pepper="p")

    def test_request_fingerprints_differ_by_body(self) -> None:
        assert fingerprint_request(b'{"amount":250000}') != fingerprint_request(
            b'{"amount":100}'
        )


# ---------------------------------------------------------------------------
# QR signing
# ---------------------------------------------------------------------------
KUID = "KA-NG-JG-BKD-2026-000123"


class TestQrSigning:
    @pytest.fixture
    def signer(self) -> QrSigner:
        return QrSigner({1: "secret-for-key-version-one"}, current_version=1)

    def test_signature_shape_carries_the_key_version(self, signer: QrSigner) -> None:
        signature = signer.sign(KUID)
        version, digest = signature.split(".")
        assert version == "1"
        assert len(digest) == 16
        assert all(c in "0123456789abcdef" for c in digest)

    def test_valid_signature_verifies(self, signer: QrSigner) -> None:
        assert signer.verify(KUID, signer.sign(KUID)).valid is True

    def test_signature_is_bound_to_its_kuid(self, signer: QrSigner) -> None:
        # Lifting a signature from one card onto another KUID must fail, or the
        # "issued by KAFRIADA" mark means nothing.
        other = "KA-NG-JG-BKD-2026-000999"
        assert signer.verify(other, signer.sign(KUID)).valid is False

    @pytest.mark.parametrize(
        "bad",
        [
            None, "", "garbage", "1.short", "1." + "f" * 16, "0.aaaaaaaaaaaaaaaa",
            "1.AAAAAAAAAAAAAAAA",  # uppercase hex is not what we emit
            "9.aaaaaaaaaaaaaaaa",  # unknown key version
        ],
    )
    def test_malformed_or_forged_signatures_are_rejected(
        self, signer: QrSigner, bad: str | None
    ) -> None:
        assert signer.verify(KUID, bad).valid is False

    def test_rotation_keeps_old_cards_verifying(self) -> None:
        """The reason the version prefix exists.

        Cards printed under key 1 are in people's pockets across 27 LGAs. After
        rotating to key 2 they must keep verifying, and new cards must be signed
        with the new key.
        """
        old = QrSigner({1: "old-secret"}, current_version=1)
        printed_last_month = old.sign(KUID)

        rotated = QrSigner({1: "old-secret", 2: "new-secret"}, current_version=2)

        old_check = rotated.verify(KUID, printed_last_month)
        assert old_check.valid is True
        assert old_check.retired_key is True, "should be flagged for re-issue"

        new_check = rotated.verify(KUID, rotated.sign(KUID))
        assert new_check.valid is True
        assert new_check.retired_key is False

    def test_refuses_to_build_without_a_secret_for_the_current_version(self) -> None:
        with pytest.raises(ValueError, match="no secret for current key version"):
            QrSigner({1: "a"}, current_version=2)


# ---------------------------------------------------------------------------
# Paystack webhook signature
# ---------------------------------------------------------------------------
class TestPaystackSignature:
    SECRET = "sk_test_not_a_real_key"

    def _sign(self, body: bytes) -> str:
        import hashlib
        import hmac

        return hmac.new(self.SECRET.encode(), body, hashlib.sha512).hexdigest()

    def test_genuine_signature_verifies(self) -> None:
        body = b'{"event":"charge.success","data":{"reference":"KAF-1","amount":250000}}'
        assert verify_paystack_signature(
            raw_body=body, header_signature=self._sign(body), secret_key=self.SECRET
        )

    def test_any_change_to_the_body_invalidates_it(self) -> None:
        body = b'{"event":"charge.success","data":{"reference":"KAF-1","amount":250000}}'
        signature = self._sign(body)
        tampered = body.replace(b"250000", b"000100")
        assert not verify_paystack_signature(
            raw_body=tampered, header_signature=signature, secret_key=self.SECRET
        )

    def test_reserialised_body_fails_which_is_why_we_keep_the_raw_bytes(self) -> None:
        """The bug this test exists to prevent.

        Parsing the JSON and re-serialising it changes key order and whitespace,
        so the HMAC no longer matches. It presents as "Paystack is sending bad
        signatures" and costs a day. Read ``await request.body()`` first, verify,
        then parse.
        """
        import json

        original = b'{"event":"charge.success","data":{"amount":250000}}'
        signature = self._sign(original)
        reserialised = json.dumps(json.loads(original)).encode()

        assert reserialised != original
        assert not verify_paystack_signature(
            raw_body=reserialised, header_signature=signature, secret_key=self.SECRET
        )

    @pytest.mark.parametrize("header", [None, "", "deadbeef", "  "])
    def test_missing_or_junk_signature_is_rejected(self, header: str | None) -> None:
        assert not verify_paystack_signature(
            raw_body=b"{}", header_signature=header, secret_key=self.SECRET
        )

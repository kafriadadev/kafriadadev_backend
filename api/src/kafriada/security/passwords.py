"""Password hashing.

Two rules govern everything in this module, and both come from the architecture:

1.  **Hashing never happens inside a database transaction.** Argon2id is designed
    to be expensive — roughly 50-100ms of dedicated CPU per call. The KUID counter
    is a single hot row that every registration in the state contends on, so
    holding that lock across a hash would drop registration throughput from
    hundreds per second to about four. Hash first, then open the transaction.

2.  **Concurrent hashing is capped.** Argon2id burns CPU and memory by design. On a
    2 vCPU instance, an uncapped registration drive starves every other request in
    the process, including the public profile pages being scanned at the same
    venue. The semaphore turns that collapse into a queue.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

from kafriada.settings import Settings, get_settings

# Argon2 reads the whole input, so an attacker who can post a 10MB "password"
# can burn a worker. Long passwords add no security beyond this point.
MAX_PASSWORD_BYTES = 1024
MIN_PASSWORD_LENGTH = 10


class PasswordTooLongError(ValueError):
    """Raised for inputs beyond MAX_PASSWORD_BYTES. Reject before hashing."""


@dataclass(frozen=True, slots=True)
class VerificationResult:
    ok: bool
    # Set when the stored hash used weaker parameters than we now require. The
    # caller should re-hash and store, outside the transaction, on next login.
    needs_rehash: bool = False


class PasswordService:
    """Argon2id hashing with a bounded concurrency budget."""

    def __init__(self, settings: Settings | None = None) -> None:
        cfg = settings or get_settings()
        self._hasher = PasswordHasher(
            time_cost=cfg.argon2_time_cost,
            memory_cost=cfg.argon2_memory_kib,
            parallelism=cfg.argon2_parallelism,
            hash_len=32,
            salt_len=16,
            type=Type.ID,  # Argon2id — the variant OWASP recommends
        )
        self._gate = threading.BoundedSemaphore(cfg.password_hash_concurrency)
        # Verifying a password for a user that does not exist must cost the same
        # as verifying one that does, or response timing tells an attacker which
        # phone numbers are registered. This is a real hash of a throwaway value,
        # computed once at startup and re-verified on every unknown-user login.
        self._dummy_hash = self._hasher.hash("kafriada-timing-equaliser")

    # -- hashing -------------------------------------------------------
    def hash(self, raw_password: str) -> str:
        """Return an Argon2id hash. MUST NOT be called inside a transaction."""
        self._guard_length(raw_password)
        with self._gate:
            return self._hasher.hash(raw_password)

    def verify(self, stored_hash: str, raw_password: str) -> VerificationResult:
        """Check a password against a stored hash.

        Never raises on a wrong password — a mismatch is an ordinary outcome, not
        an exceptional one, and turning it into an exception invites a caller to
        accidentally treat "error" as "authenticated".
        """
        try:
            self._guard_length(raw_password)
        except PasswordTooLongError:
            return VerificationResult(ok=False)

        with self._gate:
            try:
                self._hasher.verify(stored_hash, raw_password)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                return VerificationResult(ok=False)
            needs_rehash = self._hasher.check_needs_rehash(stored_hash)
        return VerificationResult(ok=True, needs_rehash=needs_rehash)

    def verify_dummy(self) -> None:
        """Spend the same CPU as a real verification, and discard the result.

        Call this on the "no such user" branch of sign-in so that an attacker
        cannot distinguish a registered phone number from an unregistered one by
        measuring how long the response takes.
        """
        with self._gate:
            try:
                self._hasher.verify(self._dummy_hash, "not-the-password")
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                # Expected on every call — the dummy password never matches, and
                # the point is to spend the CPU rather than to learn anything.
                # Not logged: this fires on every sign-in attempt for an unknown
                # phone number, so a log line here would be both noise and a
                # record of who tried to sign in as whom.
                return

    # -- validation ----------------------------------------------------
    @staticmethod
    def _guard_length(raw_password: str) -> None:
        if len(raw_password.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise PasswordTooLongError(
                f"password exceeds {MAX_PASSWORD_BYTES} bytes"
            )


def password_policy_error(raw_password: str) -> str | None:
    """Return a human message if the password is unacceptable, else None.

    Deliberately minimal. NIST guidance is that length beats composition rules,
    and complexity requirements push people towards predictable substitutions and
    written-down passwords. We check length, byte ceiling, and nothing else here;
    a breached-password check is a Phase 2 addition.
    """
    if len(raw_password) < MIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_PASSWORD_LENGTH} characters."
    if len(raw_password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return "That password is too long."
    if raw_password.strip() == "":
        return "Enter a password."
    return None


_service: PasswordService | None = None
_service_lock = threading.Lock()


def get_password_service() -> PasswordService:
    """Process-wide singleton. Building the hasher allocates the timing hash."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = PasswordService()
    return _service

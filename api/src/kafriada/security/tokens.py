"""Opaque tokens: session cookies, one-time codes, idempotency keys.

The rule this module exists to enforce: **the database never stores a value that
could be replayed as a credential.** Session rows hold a SHA-256 digest of the
token, not the token. Anyone who obtains a copy of the sessions table — a leaked
backup, a support export, a compromised read replica — gets a list of digests
they cannot use to sign in as anybody.

SHA-256 without a salt or a work factor is the right choice here, and only here:
these tokens are 256 bits of cryptographic randomness, so there is no dictionary
to attack and no password to guess. Argon2 is for values a human chose.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# 32 bytes = 256 bits. urlsafe_b64 gives 43 characters, cookie-safe and
# header-safe with no escaping.
TOKEN_BYTES = 32

# Numeric OTP length. Six digits is one in a million per guess, which is safe
# only because attempts are capped and the code is short-lived — the rate limit
# is what makes this secure, not the entropy.
OTP_DIGITS = 6
OTP_MAX_ATTEMPTS = 5


def new_token() -> str:
    """A fresh opaque token. Show this to the client exactly once."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(raw_token: str) -> str:
    """Digest for storage. Deterministic, so it can be looked up by index."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    """Constant-time comparison.

    Python's ``==`` on strings short-circuits at the first differing byte, which
    leaks how much of a guess was correct. Never compare a secret with ``==``.
    """
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def new_otp() -> str:
    """A numeric one-time code, uniformly random and zero-padded.

    ``secrets.randbelow`` rather than ``random`` — the stdlib ``random`` module is
    a Mersenne Twister, and its output is fully predictable from previous values.
    """
    return f"{secrets.randbelow(10**OTP_DIGITS):0{OTP_DIGITS}d}"


def hash_otp(code: str, *, pepper: str) -> str:
    """Digest an OTP for storage, bound to a server-held pepper.

    A six-digit code has only a million possibilities, so a bare digest of it is
    trivially reversible with a lookup table. Keying the digest with a secret the
    database does not contain means a stolen table alone does not reveal codes in
    flight.
    """
    return hmac.new(
        pepper.encode("utf-8"), code.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def new_idempotency_key() -> str:
    """Client-side key for a mutating request, so a retry cannot double-charge."""
    return secrets.token_urlsafe(16)


def fingerprint_request(body: bytes) -> str:
    """Digest of a request body, stored alongside an idempotency key.

    A key replayed with a *different* body is a client bug, and silently
    accepting it is how money doubles. Comparing fingerprints turns that into a
    422 instead of a second charge.
    """
    return hashlib.sha256(body).hexdigest()

"""Opaque single-use token generation + hashing (Sprint 6 T5, D-028).

Email verification and password-reset tokens are high-entropy random strings.
We store only their SHA-256 hash (like a session token, not a password): the raw
token lives only in the email link. SHA-256 is correct here — unlike a password
these are already 256 bits of entropy, so a slow KDF buys nothing and lookup by
hash must be a single indexed query.
"""

from __future__ import annotations

import hashlib
import secrets


def generate_token() -> str:
    """A fresh URL-safe token (~256 bits) to embed in an email link."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """SHA-256 hex digest of the raw token, for at-rest storage + lookup."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

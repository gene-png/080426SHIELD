"""Argon2id password hashing.

Master Spec §4.5: passwords stored with a memory-hard KDF; rotated
parameters require no migration (Argon2's encoded hash carries its own
parameters, so a verify call rehashes transparently when parameters drift).

OWASP Password Storage Cheat Sheet (2023) recommends Argon2id with:
  - memory cost m >= 19 MiB
  - time cost t >= 2
  - parallelism p = 1
We exceed those defaults slightly to give a comfortable margin.

A successful `verify_password` returns (True, needs_rehash). Callers must
check `needs_rehash` and re-hash + persist when True so that hardware
generations don't leave old hashes unprotected.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# Tuned for ~50-100 ms on a 2024-era server. Re-tune at deploy time per
# Master Spec §4.5; the encoded hash carries the parameters so old hashes
# stay verifiable across re-tunes.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,  # 64 MiB
    parallelism=1,
    hash_len=32,
    salt_len=16,
)


class PasswordPolicyError(ValueError):
    """Raised when a candidate password fails the policy gate."""


MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256  # cap to defend against DoS via gigantic input


def _check_policy(password: str) -> None:
    if not isinstance(password, str):
        raise PasswordPolicyError("Password must be a string.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
    # A full HIBP top-100k check belongs in a Phase 6 hardening pass.
    # Cover the obvious offenders here so even dev fixtures fail policy.
    lower = password.lower()
    if lower in {"password1234", "letmein12345", "qwertyuiopas"}:
        raise PasswordPolicyError("Password is in the deny list.")


def hash_password(password: str) -> str:
    """Apply the password policy and return the encoded Argon2id hash."""
    _check_policy(password)
    return _hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> tuple[bool, bool]:
    """Verify `password` against `encoded_hash`.

    Returns:
        (matched, needs_rehash). `needs_rehash` is True when the stored hash
        was produced with weaker parameters than the current `_hasher` is
        configured with - the caller is expected to re-hash and update the
        user row.
    """
    try:
        _hasher.verify(encoded_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False, False
    needs_rehash = _hasher.check_needs_rehash(encoded_hash)
    return True, needs_rehash

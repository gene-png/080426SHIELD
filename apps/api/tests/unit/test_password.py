"""Password hashing + policy."""

from __future__ import annotations

import pytest

from app.security.password import (
    PasswordPolicyError,
    hash_password,
    verify_password,
)


@pytest.mark.unit
def test_hash_then_verify_roundtrip() -> None:
    h = hash_password("correct horse battery staple!")
    matched, needs_rehash = verify_password("correct horse battery staple!", h)
    assert matched is True
    assert needs_rehash is False


@pytest.mark.unit
def test_verify_rejects_wrong_password() -> None:
    h = hash_password("correct horse battery staple!")
    matched, needs_rehash = verify_password("wrong horse battery staple!", h)
    assert matched is False
    assert needs_rehash is False


@pytest.mark.unit
def test_hash_produces_unique_output_each_call() -> None:
    h1 = hash_password("same password every time!")
    h2 = hash_password("same password every time!")
    assert h1 != h2, "hashes must be salted; identical inputs must not collide"


@pytest.mark.unit
def test_policy_rejects_short_password() -> None:
    with pytest.raises(PasswordPolicyError, match="at least"):
        hash_password("short")


@pytest.mark.unit
def test_policy_rejects_oversized_password() -> None:
    with pytest.raises(PasswordPolicyError, match="at most"):
        hash_password("a" * 257)


@pytest.mark.unit
def test_policy_rejects_deny_list() -> None:
    with pytest.raises(PasswordPolicyError, match="deny list"):
        hash_password("password1234")


@pytest.mark.unit
def test_verify_handles_malformed_hash_gracefully() -> None:
    matched, needs_rehash = verify_password("any password 12345", "not-a-real-hash")
    assert matched is False
    assert needs_rehash is False

"""Unit tests for the TOTP / secret-encryption / recovery-code primitives.

Correctness of the TOTP core is locked to the RFC 6238 published test vector
(SHA1, secret "12345678901234567890"). See Sprint 6 T4 / D-027.
"""

from __future__ import annotations

import base64

import pytest

from app.security import totp

# RFC 6238 Appendix B, SHA1 variant: the ASCII secret "12345678901234567890".
_RFC_SECRET_B32 = base64.b32encode(b"12345678901234567890").decode("ascii")


@pytest.mark.unit
def test_totp_matches_rfc6238_vector() -> None:
    # RFC 6238: at T=59s (step 1) the 6-digit SHA1 TOTP is 287082.
    assert totp.totp_now(_RFC_SECRET_B32, at=59) == "287082"
    # At T=1111111109s the 6-digit code is 081804.
    assert totp.totp_now(_RFC_SECRET_B32, at=1111111109) == "081804"


@pytest.mark.unit
def test_generate_secret_is_valid_base32() -> None:
    secret = totp.generate_secret()
    # Decodable as base32 (with padding) and non-trivial length.
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    assert base64.b32decode(padded)
    assert len(secret) >= 16


@pytest.mark.unit
def test_verify_totp_accepts_current_and_rejects_wrong() -> None:
    secret = totp.generate_secret()
    now = 1_600_000_000
    code = totp.totp_now(secret, at=now)
    assert totp.verify_totp(secret, code, at=now) is True
    assert totp.verify_totp(secret, "000000", at=now) is False
    assert totp.verify_totp(secret, "not-digits", at=now) is False


@pytest.mark.unit
def test_verify_totp_tolerates_one_step_skew_but_not_two() -> None:
    secret = totp.generate_secret()
    now = 1_600_000_000
    prev = totp.totp_now(secret, at=now - 30)
    two_ago = totp.totp_now(secret, at=now - 90)
    assert totp.verify_totp(secret, prev, at=now) is True
    assert totp.verify_totp(secret, two_ago, at=now) is False


@pytest.mark.unit
def test_secret_encrypt_roundtrip() -> None:
    secret = totp.generate_secret()
    ciphertext = totp.encrypt_secret(secret)
    assert ciphertext != secret
    assert totp.decrypt_secret(ciphertext) == secret


@pytest.mark.unit
def test_decrypt_bad_ciphertext_raises_loudly() -> None:
    with pytest.raises(RuntimeError):
        totp.decrypt_secret("not-a-valid-fernet-token")


@pytest.mark.unit
def test_provisioning_uri_shape() -> None:
    uri = totp.provisioning_uri("ABCDEFGH", "user@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "secret=ABCDEFGH" in uri
    assert "issuer=" in uri


@pytest.mark.unit
def test_recovery_codes_generate_and_hash_verify() -> None:
    codes = totp.generate_recovery_codes()
    assert len(codes) == 10
    assert len(set(codes)) == 10  # unique
    code = codes[0]
    code_hash = totp.hash_recovery_code(code)
    assert code_hash != code
    assert totp.verify_recovery_code(code, code_hash) is True
    # Case/whitespace-insensitive match; wrong code fails.
    assert totp.verify_recovery_code(f"  {code.lower()} ", code_hash) is True
    assert totp.verify_recovery_code("ZZZZ-ZZZZ", code_hash) is False

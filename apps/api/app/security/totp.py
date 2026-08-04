"""TOTP (RFC 6238) + secret encryption + recovery codes for MFA (Sprint 6 T4, D-027).

Implemented against the stdlib (``hmac``/``hashlib``/``struct``/``base64``) rather
than adding a third-party OTP dependency: RFC 6238 is a thin HMAC-of-a-counter and
we lock correctness to the RFC's published test vectors in the unit suite. Codes
are the standard SHA1 / 6-digit / 30-second shape every authenticator app expects.

The TOTP secret is encrypted at rest with Fernet (``cryptography``, already a
transitive dependency via ``python-jose[cryptography]``). The Fernet key is derived
deterministically from ``JWT_SIGNING_SECRET`` so no new secret has to be provisioned;
rotating the signing secret invalidates stored MFA secrets (users re-enroll), which
is the correct, loud failure mode rather than a silent decrypt error.

"AI suggests, code computes" — none of this touches the LLM egress path; it is pure
deterministic crypto.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.logging import get_logger

log = get_logger("app.security.totp")

_DIGITS = 6
_PERIOD_SECONDS = 30
_ISSUER = "SHIELD by Kentro"
# Unambiguous alphabet for recovery codes (no 0/O/1/I/L) so a human can copy them.
_RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_RECOVERY_CODE_COUNT = 10


# -----------------------------------------------------------------------------
# TOTP core (RFC 6238 / RFC 4226)
# -----------------------------------------------------------------------------


def generate_secret() -> str:
    """A fresh base32 TOTP secret (160 bits, the RFC-recommended size)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int, digits: int = _DIGITS) -> str:
    """RFC 4226 HOTP: HMAC-SHA1 of the 8-byte counter, dynamically truncated."""
    # Base32 alphabet requires padding to a multiple of 8 chars to decode.
    padded = secret_b32.upper() + "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(padded)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**digits)).zfill(digits)


def totp_now(secret_b32: str, *, at: float | None = None) -> str:
    """The current TOTP code for ``secret_b32`` (used by tests + the live smoke)."""
    ts = time.time() if at is None else at
    return _hotp(secret_b32, int(ts) // _PERIOD_SECONDS)


def verify_totp(
    secret_b32: str, code: str, *, valid_window: int = 1, at: float | None = None
) -> bool:
    """True if ``code`` matches the TOTP for the current step (±``valid_window``).

    A ±1 window (default) tolerates the usual clock skew between the server and
    the authenticator. Comparison is constant-time to avoid a timing oracle.
    """
    candidate = (code or "").strip().replace(" ", "")
    if not candidate.isdigit() or len(candidate) != _DIGITS:
        return False
    ts = time.time() if at is None else at
    step = int(ts) // _PERIOD_SECONDS
    for drift in range(-valid_window, valid_window + 1):
        if hmac.compare_digest(candidate, _hotp(secret_b32, step + drift)):
            return True
    return False


def provisioning_uri(secret_b32: str, account_name: str, *, issuer: str = _ISSUER) -> str:
    """otpauth:// URI for the QR code an authenticator app scans."""
    label = quote(f"{issuer}:{account_name}")
    params = urlencode(
        {
            "secret": secret_b32,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": _DIGITS,
            "period": _PERIOD_SECONDS,
        }
    )
    return f"otpauth://totp/{label}?{params}"


# -----------------------------------------------------------------------------
# Secret encryption at rest
# -----------------------------------------------------------------------------


def _fernet() -> Fernet:
    signing_secret = get_settings().jwt_signing_secret.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(signing_secret).digest())
    return Fernet(key)


def encrypt_secret(plaintext_secret: str) -> str:
    """Encrypt a base32 TOTP secret for storage in ``users.mfa_totp_secret``."""
    return _fernet().encrypt(plaintext_secret.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a stored TOTP secret. Raises loudly if the token is unreadable."""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        # A stored secret that no longer decrypts is a real error (e.g. the
        # signing secret rotated). Fail loud so the operator sees it, rather
        # than silently treating MFA as absent.
        log.error("totp.secret_decrypt_failed")
        raise RuntimeError("Stored MFA secret could not be decrypted.") from exc


# -----------------------------------------------------------------------------
# Recovery codes
# -----------------------------------------------------------------------------


def generate_recovery_codes(count: int = _RECOVERY_CODE_COUNT) -> list[str]:
    """One-time recovery codes shown once at enrollment. Format ``XXXX-XXXX``."""

    def _group() -> str:
        return "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4))

    return [f"{_group()}-{_group()}" for _ in range(count)]


def normalize_recovery_code(code: str) -> str:
    """Canonical form for hashing/compare: uppercase, whitespace stripped."""
    return (code or "").strip().upper().replace(" ", "")


# Recovery codes are hashed with Argon2id like passwords, but through a
# dedicated hasher: they are high-entropy machine-generated strings shorter
# than the 12-char password policy, so ``password.hash_password`` (which
# enforces that policy) cannot be reused. Stored hashed, never plaintext.
_recovery_hasher = PasswordHasher()


def hash_recovery_code(code: str) -> str:
    """Argon2id hash of the normalized recovery code, for at-rest storage."""
    return _recovery_hasher.hash(normalize_recovery_code(code))


def verify_recovery_code(code: str, code_hash: str) -> bool:
    """Constant-time-ish Argon2 verify of a candidate recovery code."""
    try:
        _recovery_hasher.verify(code_hash, normalize_recovery_code(code))
        return True
    except (VerifyMismatchError, InvalidHashError):
        return False

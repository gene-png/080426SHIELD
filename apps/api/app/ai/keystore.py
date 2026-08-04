"""Runtime provider API-key storage (issue 2).

The single place that knows how a pasted API key is encrypted, validated, and
resolved. Three rules hold everywhere in this module:

1. **Validate before storing.** ``validate_key`` makes a real, minimal provider
   call. A key the provider rejects is never written, so a typo cannot silently
   take AI offline — the admin gets a typed error instead (FAIL LOUDLY).
2. **Never return the key.** ``load_key`` exists so the provider adapter can
   decrypt at call time. Nothing surfaces it to an endpoint, a log line, or an
   audit ``details`` blob.
3. **Database beats environment.** A key pasted through the UI overrides
   ``ANTHROPIC_API_KEY`` and friends, so removing it through the UI is a real
   removal rather than a silent fallback to whatever the container booted with.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models.llm_credential import LlmCredential

logger = logging.getLogger(__name__)

# Which env var backs each provider, for the "environment" key source.
_ENV_KEY_ATTR = {
    "anthropic": "anthropic_api_key",
    "openai": "openai_api_key",
    "gemini": "gemini_api_key",
}


def _fernet(settings: Settings) -> Fernet:
    """Derive the encryption key from the deployment's JWT signing secret.

    Reuses an existing deployment secret rather than inventing a second one an
    operator could forget to set: if ``JWT_SIGNING_SECRET`` is rotated, stored
    provider keys become undecryptable and the admin re-pastes — an acceptable
    and loud failure, and strictly better than a hard-coded default. Production
    already refuses to boot on the placeholder secret
    (``assert_safe_for_runtime``), so this inherits that guarantee.
    """
    digest = hashlib.sha256(settings.jwt_signing_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def store_key(
    db: Session,
    *,
    provider: str,
    api_key: str,
    actor_user_id: uuid.UUID | None,
    settings: Settings | None = None,
) -> LlmCredential:
    """Encrypt and upsert the key for ``provider``. Caller validates first."""
    s = settings or get_settings()
    token = _fernet(s).encrypt(api_key.encode("utf-8")).decode("ascii")
    row = db.execute(
        select(LlmCredential).where(LlmCredential.provider == provider)
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if row is None:
        row = LlmCredential(provider=provider, encrypted_key=token)
        db.add(row)
    else:
        row.encrypted_key = token
    row.set_by_user_id = actor_user_id
    row.last_validated_at = now
    db.flush()
    logger.info("llm.keystore.stored provider=%s by=%s", provider, actor_user_id)
    return row


def delete_key(db: Session, *, provider: str) -> bool:
    """Remove the stored key. Returns whether a row was actually removed."""
    row = db.execute(
        select(LlmCredential).where(LlmCredential.provider == provider)
    ).scalar_one_or_none()
    if row is None:
        logger.info("llm.keystore.delete_noop provider=%s", provider)
        return False
    db.delete(row)
    db.flush()
    logger.info("llm.keystore.removed provider=%s", provider)
    return True


def load_key(db: Session, *, provider: str, settings: Settings | None = None) -> str | None:
    """Decrypt the stored key, or None when there isn't one.

    A row that will not decrypt (rotated ``JWT_SIGNING_SECRET``) is reported as
    absent AND logged loudly — the admin sees "AI is not live" and re-pastes,
    rather than every Run-AI failing with an opaque provider 401.
    """
    row = db.execute(
        select(LlmCredential).where(LlmCredential.provider == provider)
    ).scalar_one_or_none()
    if row is None:
        return None
    s = settings or get_settings()
    try:
        return _fernet(s).decrypt(row.encrypted_key.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.error(
            "llm.keystore.undecryptable provider=%s — JWT_SIGNING_SECRET likely rotated; "
            "the admin must re-enter the API key",
            provider,
        )
        return None


def key_source(db: Session, *, provider: str, settings: Settings | None = None) -> str:
    """Where the effective key comes from: 'database' | 'environment' | 'none'."""
    if load_key(db, provider=provider, settings=settings) is not None:
        return "database"
    s = settings or get_settings()
    attr = _ENV_KEY_ATTR.get(provider)
    if attr and getattr(s, attr, ""):
        return "environment"
    return "none"


def effective_key(db: Session, *, provider: str, settings: Settings | None = None) -> str:
    """The key to actually call the provider with. DB wins over environment."""
    stored = load_key(db, provider=provider, settings=settings)
    if stored:
        return stored
    s = settings or get_settings()
    attr = _ENV_KEY_ATTR.get(provider)
    return getattr(s, attr, "") if attr else ""


# --- validation ------------------------------------------------------------

KeyValidator = Callable[[str, str, str], tuple[bool, str]]


def live_validate_key(provider: str, model: str, api_key: str) -> tuple[bool, str]:
    """Confirm a key works by making the smallest real call the provider allows.

    Returns ``(ok, human_detail)`` and never raises — a network blip must
    surface as a readable refusal in the admin UI, not a 500. Deliberately
    tiny: one token of output is enough to prove the credential is accepted.
    """
    if provider == "anthropic":
        try:
            import anthropic
        except ImportError:
            return False, "The 'anthropic' SDK is not installed in the api image."
        try:
            client = anthropic.Anthropic(api_key=api_key)
            client.messages.create(
                model=model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True, f"Validated against {provider}/{model}."
        except Exception as exc:  # noqa: BLE001 - any failure is a failed validation
            return False, _readable_provider_error(exc)
    # openai / gemini / vertex adapters exist in llm.py but have no cheap
    # validation probe yet. Say so rather than pretend the key was checked.
    return (
        False,
        f"Automatic key validation is not implemented for provider {provider!r} yet — "
        "set SHIELD_LLM_PROVIDER to 'anthropic' or supply the key via environment.",
    )


def _readable_provider_error(exc: Exception) -> str:
    """Turn a provider exception into copy an admin can act on."""
    status = getattr(exc, "status_code", None)
    if status == 401:
        return "The provider rejected this key (401). Check you pasted it in full."
    if status == 403:
        return "The provider accepted the key but denied access (403). Check its permissions."
    if status == 404:
        return "The provider rejected the configured model (404). Check SHIELD_LLM_MODEL."
    if status == 429:
        return "The provider rate-limited the validation call (429). Try again shortly."
    return f"Could not validate the key: {type(exc).__name__}: {exc}"


def get_key_validator() -> KeyValidator:
    """FastAPI dependency so tests can substitute a validator that never calls out."""
    return live_validate_key

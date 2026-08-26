"""Settings loaded from environment. Master Spec §4.4-§4.5; AI Prompt §6.14.

No setting may be hardcoded. Every external service and security knob is here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production"]
RedactionMode = Literal["strict", "standard", "off"]
LLMProvider = Literal["anthropic", "openai", "azure_openai", "bedrock", "gemini", "vertex", "local"]

# OAuth scope required for Vertex AI generateContent calls (D-029).
_GCP_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

# Model ids that were once shipped as defaults but are not valid at any live
# provider. Booting live against one of these guarantees a 404 on the first
# real call (D-026), so the preflight refuses rather than fail on first use.
_KNOWN_PLACEHOLDER_MODELS = frozenset({"claude-opus-4-7"})


def _anthropic_sdk_importable() -> bool:
    """True if the ``anthropic`` SDK can be imported without importing it.

    Isolated as a module-level helper so the live-mode boot preflight can be
    unit-tested by monkeypatching it (the SDK is installed in the api image but
    absent from some tool environments)."""
    from importlib.util import find_spec

    return find_spec("anthropic") is not None


def _google_auth_importable() -> bool:
    """True if the ``google-auth`` library can be imported (D-029).

    Mirrors ``_anthropic_sdk_importable`` — isolated as a module-level helper so
    the Vertex live-mode boot preflight can be unit-tested by monkeypatching it.
    ``google.auth`` is installed in the api image but absent from some tool
    environments."""
    from importlib.util import find_spec

    return find_spec("google.auth") is not None


def _adc_resolvable() -> bool:
    """True if Application Default Credentials resolve for the Vertex provider.

    Isolated as a module-level helper so the boot preflight is unit-testable by
    monkeypatching it. Resolving ADC only discovers the credential source (env
    var, gcloud config, metadata server) — it does NOT fetch a token, so this is
    a cheap, network-free probe. Returns a bool and never raises: the loud
    failure is raised by ``assert_safe_for_runtime`` when this is false."""
    try:
        import google.auth
        from google.auth.exceptions import GoogleAuthError
    except ImportError:
        return False
    try:
        credentials, _project = google.auth.default(scopes=[_GCP_CLOUD_PLATFORM_SCOPE])
    except GoogleAuthError:
        return False
    return credentials is not None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Runtime
    environment: Environment = "development"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+psycopg://shield:shield@db:5432/shield"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Object storage
    s3_endpoint_url: str = "http://minio:9000"
    s3_bucket: str = "shield-artifacts"
    s3_access_key: str = "shield-minio"
    s3_secret_key: str = (
        "shield-minio-secret"  # noqa: S105 - dev placeholder, refused in prod via assert_safe_for_runtime
    )
    s3_kms_key_id: str = "dev-stub-key"

    # OIDC (Keycloak) — hybrid SSO exchange (Sprint 9 T4, D-032). The exchange
    # verifies a Keycloak ACCESS token against `keycloak_jwks_url` (network only —
    # never compared to `iss`), pinning `iss` to `keycloak_issuer`, `aud` to
    # `keycloak_audience`, and `azp` to `keycloak_client_id`.
    # Split-horizon (Sprint 9 T5): `keycloak_issuer` is the CANONICAL
    # browser-facing issuer pinned as `iss` (matches KC_HOSTNAME); the token the
    # exchange verifies carries this value no matter which interface minted it.
    # `keycloak_jwks_url` is the CONTAINER-reachable fetch endpoint the verifier
    # hits for signing keys — a deliberately different horizon.
    keycloak_issuer: str = "http://localhost:8080/realms/shield"
    keycloak_audience: str = "shield-api"
    keycloak_client_id: str = "shield-web"
    keycloak_jwks_url: str = "http://keycloak:8080/realms/shield/protocol/openid-connect/certs"

    # LLM (Master Spec §4.4 - never hardcoded)
    shield_llm_provider: LLMProvider = "anthropic"
    shield_llm_model: str = "claude-sonnet-5"
    shield_llm_mode: Literal["fixture", "live"] = "fixture"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    # Vertex AI via Application Default Credentials (D-029) — NO static API key.
    # The `gemini` provider (API key) and `vertex` provider (ADC) are distinct.
    gcp_project_id: str = ""
    gcp_region: str = "us-central1"

    # Feature flags (Master Spec §2 - deferred for v1)
    shield_auth_require_mfa: bool = False
    shield_auth_require_email_verify: bool = False
    shield_email_delivery_enabled: bool = False
    # Hybrid Keycloak SSO (Sprint 9 T4, D-032). Default OFF: the credentials
    # stack is untouched and NO Keycloak network is touched. Flipping it on
    # registers POST /auth/oidc/exchange as a live door and requires a coherent
    # Keycloak config (checked at boot by oidc_readiness). Keycloak tokens are
    # NEVER accepted as API bearers — the exchange mints a plain D-020 pair.
    shield_auth_oidc_enabled: bool = False

    # Redaction (Master Spec §12)
    shield_redaction_mode: RedactionMode = "strict"

    # Session security (Master Spec §4.5)
    # 3600, raised from 900 on 2026-08-08. The old 15 minutes was not itself the
    # problem — the web rotates the access token automatically — but it made the
    # rotation race below fire four times an hour, which is what users
    # experienced as "the page logs me out while I am working".
    jwt_access_ttl_seconds: int = Field(default=3600, ge=60)
    # MUST comfortably exceed jwt_access_ttl_seconds. At the old 1800 against a
    # 3600 access TTL the refresh token would die half an hour BEFORE the token
    # it exists to renew, guaranteeing a hard logout with no recovery path.
    # 86400 aligns it with shield_forced_reauth_seconds, so the daily ceiling —
    # not an incidental TTL — is what actually bounds a session.
    jwt_refresh_ttl_seconds: int = Field(default=86400, ge=300)
    # Rotation grace. A refresh token is single-use, but a browser routinely
    # fires several requests at once when the access token expires, and every
    # one of them presents the SAME refresh token. The first rotates it and the
    # rest were rejected as replay — observed in production logs as pairs of
    # `auth.refresh_reused` 286 MICROSECONDS apart, each ending in a hard
    # sign-out. Within this window the immediately-previous jti is accepted and
    # the CURRENT pair is re-issued (no further rotation), so concurrent callers
    # converge instead of knocking each other out. Set to 0 to restore strict
    # single-use. See `refresh()` in routes/auth.py for the security envelope.
    jwt_refresh_grace_seconds: int = Field(default=60, ge=0)
    # Short-lived token issued after the password factor when MFA is enrolled;
    # exchanged for the full pair by POST /auth/mfa/verify-login (Sprint 6 T4).
    jwt_mfa_pending_ttl_seconds: int = Field(default=300, ge=60)
    shield_account_lockout_max_attempts: int = Field(default=10, ge=1)
    shield_account_lockout_window_seconds: int = Field(default=900, ge=60)
    shield_idle_timeout_seconds: int = Field(default=1800, ge=60)
    shield_forced_reauth_seconds: int = Field(default=86400, ge=300)

    # Rate limiting (Sprint 3 T3). Fixed-window per-IP + per-account on the auth
    # endpoints and per-client on the expensive run-AI path. Defaults are
    # deliberately generous so the serialized e2e suite (all traffic from one
    # localhost IP, one seeded admin account) never trips them; tighten per
    # environment via env vars. Redis-backed; fail-open on a Redis outage.
    shield_rate_limit_enabled: bool = True
    shield_rate_limit_auth_ip_max: int = Field(default=300, ge=1)
    shield_rate_limit_auth_ip_window_seconds: int = Field(default=60, ge=1)
    shield_rate_limit_auth_account_max: int = Field(default=100, ge=1)
    shield_rate_limit_auth_account_window_seconds: int = Field(default=60, ge=1)
    shield_rate_limit_ai_max: int = Field(default=60, ge=1)
    shield_rate_limit_ai_window_seconds: int = Field(default=60, ge=1)

    # JWT signing
    jwt_signing_secret: str = (
        "dev-only-replace-via-secrets-manager"  # noqa: S105 - dev placeholder; refused by assert_safe_for_runtime on ANY non-development environment (#142 - this comment used to say "in prod", which was true and was the reason nobody checked staging)
    )

    # Mail (MailHog in dev)
    smtp_host: str = "mailhog"
    smtp_port: int = 1025
    smtp_from: str = "no-reply@shield.local"
    # Base URL the web app is reachable at, used to build email verification /
    # password-reset links (Sprint 6 T5, D-028).
    web_base_url: str = "http://localhost:3000"
    # Single-use email-token lifetimes (D-028). Verification is generous (a user
    # may not check mail immediately); reset is short (a live reset link is a
    # bearer credential).
    email_verify_token_ttl_seconds: int = Field(default=86400, ge=300)
    password_reset_token_ttl_seconds: int = Field(default=3600, ge=300)

    def is_development(self) -> bool:
        """True only on a developer's machine.

        THE SAFE PREDICATE, and the reason it exists (#142). Four call sites
        asked `is_production()` while meaning "is this anything other than a
        developer's machine", and `Environment` has THREE members -- so
        `staging` got the developer's treatment on all four: the egress redactor
        could be disabled, the placeholder JWT signing secret was accepted, and
        `/docs` plus `/openapi.json` were published.

        Anything that relaxes a security control keys on this. Written as a
        whitelist of one so that adding a fourth `Environment` member cannot
        silently reopen any of them -- a new member is not development, so it
        gets the safe branch by construction.

        `is_production()` was REMOVED rather than left beside this. It had zero
        callers once the four were converted, and a dead predicate that four
        things had just misused by name is a trap for whoever reaches for it
        next.

        WHEN TO BRING IT BACK, and the tell that you need to. The two predicates
        are not redundant; they are a pair with opposite jobs:

          * `is_development()` guards a RELAXATION -- something safe only on a
            developer's machine. All four #142 sites were relaxations.
          * `is_production()` guards an ENABLEMENT -- something that should
            happen only in production.

        **The BODY distinguishes them, not the `not`.** Both correct uses of
        this predicate are literally `if not self.is_development(): raise ...`
        -- an earlier draft of this docstring said the `not` itself was the tell,
        which would have had a reader "fix" the two guards it exists to protect.

        The test is what the branch DOES. Refusing to boot is a relaxation being
        withheld and reads correctly as `not is_development()`. Doing something
        extra is an enablement and needs `is_production()`: "send real email only
        in production" written as `if not settings.is_development(): send_real()`
        starts mailing real addresses from staging -- #142 with the sign flipped,
        arriving the same way, by someone taking the nearest predicate rather
        than the right one. Reintroduce `is_production()` for that case, with a
        docstring saying it guards an enablement.

        (No such site exists today -- email delivery is gated on the explicit
        `shield_email_delivery_enabled` flag, and nothing in `app/` writes
        `not is_development()`. The example is the shape to watch for, not a
        known bug.)
        """
        return self.environment == "development"

    def expose_api_docs(self) -> bool:
        """Whether to serve `/docs` and `/openapi.json`.

        Development only. On a platform that returns 404 rather than 403 so
        existence never leaks, publishing the full route inventory hands over
        the map those 404s refuse to draw.
        """
        return self.is_development()

    def live_llm_readiness(self) -> tuple[bool, str]:
        """Whether a live provider call will actually succeed (D-026).

        Returns ``(ready, human_detail)`` and never raises — the single source
        of truth shared by the boot preflight (which wraps a false result in a
        loud ``RuntimeError``) and ``GET /admin/ai-status`` (which surfaces the
        detail to an operator). Mirrors the ``_build_provider`` branch logic in
        ``app/ai/llm.py``: anthropic needs its key AND an importable SDK;
        openai/gemini are httpx adapters that need only their key; every other
        provider value has no live adapter yet.
        """
        provider = self.shield_llm_provider
        if provider == "anthropic":
            if not self.anthropic_api_key:
                return False, "Live mode is on but ANTHROPIC_API_KEY is not set."
            if not _anthropic_sdk_importable():
                return (
                    False,
                    "Live mode is on but the 'anthropic' SDK is not importable — add it "
                    "to apps/api dependencies and rebuild the api image.",
                )
        elif provider == "openai":
            if not self.openai_api_key:
                return False, "Live mode is on but OPENAI_API_KEY is not set."
        elif provider == "gemini":
            if not self.gemini_api_key:
                return False, "Live mode is on but GEMINI_API_KEY is not set."
        elif provider == "vertex":
            # Vertex uses ADC, not an API key: needs a project, the google-auth
            # library, and resolvable credentials (D-029).
            if not self.gcp_project_id:
                return False, "Live mode is on but GCP_PROJECT_ID is not set (Vertex provider)."
            if not _google_auth_importable():
                return (
                    False,
                    "Live mode is on but the 'google-auth' library is not importable — add it "
                    "to apps/api dependencies and rebuild the api image.",
                )
            if not _adc_resolvable():
                return (
                    False,
                    "Live mode is on but Application Default Credentials are not resolvable — "
                    "run 'gcloud auth application-default login' and bind-mount the gcloud "
                    "config into the api container.",
                )
        else:
            return (
                False,
                f"Live mode is on but provider {provider!r} has no live adapter yet "
                "(use anthropic, openai, gemini, or vertex, or switch SHIELD_LLM_MODE "
                "to fixture).",
            )
        if self.shield_llm_model in _KNOWN_PLACEHOLDER_MODELS:
            return (
                False,
                f"Live mode is on but SHIELD_LLM_MODEL={self.shield_llm_model!r} is a "
                "known-invalid placeholder — set a current model id.",
            )
        if not self.shield_llm_model.strip():
            return False, "Live mode is on but SHIELD_LLM_MODEL is empty."
        return True, f"Live AI configured ({provider}/{self.shield_llm_model})."

    def oidc_readiness(self) -> tuple[bool, str]:
        """Whether the hybrid OIDC exchange is coherently configured (D-032).

        Returns ``(ready, human_detail)`` and NEVER raises — the single source of
        truth shared by the boot preflight (which wraps a false result in a loud
        ``RuntimeError``) and T5's ``/ready`` keycloak probe. This is a
        config-SHAPE check only: like ``live_llm_readiness`` it makes NO network
        call (the api has no ``depends_on: keycloak`` and must not crash-loop on a
        cold ``compose up`` — a Keycloak outage surfaces as a runtime 503, not a
        boot failure). ``keycloak_jwks_url`` is the fetch endpoint; ``iss``/``aud``
        are the pinned claim values.
        """
        issuer = self.keycloak_issuer.strip()
        if not issuer:
            return False, "OIDC is enabled but KEYCLOAK_ISSUER is empty."
        if not (issuer.startswith("http://") or issuer.startswith("https://")):
            return (
                False,
                f"OIDC is enabled but KEYCLOAK_ISSUER={self.keycloak_issuer!r} is not an "
                "http(s) URL.",
            )
        jwks_url = self.keycloak_jwks_url.strip()
        if not jwks_url:
            return False, "OIDC is enabled but KEYCLOAK_JWKS_URL is empty."
        if not (jwks_url.startswith("http://") or jwks_url.startswith("https://")):
            return (
                False,
                f"OIDC is enabled but KEYCLOAK_JWKS_URL={self.keycloak_jwks_url!r} is not an "
                "http(s) URL.",
            )
        if not self.keycloak_audience.strip():
            return False, "OIDC is enabled but KEYCLOAK_AUDIENCE is empty."
        if not self.keycloak_client_id.strip():
            return False, "OIDC is enabled but KEYCLOAK_CLIENT_ID is empty."
        return True, f"Hybrid OIDC configured (issuer {issuer})."

    def assert_safe_for_runtime(self) -> None:
        """Reject obviously unsafe configurations at startup."""
        if not self.is_development() and self.shield_redaction_mode == "off":
            raise RuntimeError(
                f"SHIELD_REDACTION_MODE=off is forbidden when "
                f"ENVIRONMENT={self.environment!r} (Master Spec §12). It is "
                f"permitted only on 'development'."
            )
        if not self.is_development() and self.jwt_signing_secret.startswith("dev-only"):
            raise RuntimeError(
                f"JWT_SIGNING_SECRET is still the default placeholder and "
                f"ENVIRONMENT={self.environment!r}. A real secret is required "
                f"on anything but 'development'."
            )
        # Feature flags gate ENFORCEMENT, not boot, as of Sprint 6 (D-027/D-028):
        # shield_auth_require_mfa and shield_auth_require_email_verify now have real
        # flows behind them (routes/auth.py), so the flag requires the control at
        # login rather than refusing to start. The old boot-refusals are removed.
        #
        # Email delivery, however, still fails loudly on obvious misconfiguration:
        # turning delivery on without an SMTP host would silently drop every
        # verification / reset email — worse than refusing (D-028).
        if self.shield_email_delivery_enabled and not self.smtp_host.strip():
            raise RuntimeError(
                "SHIELD_EMAIL_DELIVERY_ENABLED=true but SMTP_HOST is empty. Configure "
                "SMTP (MailHog in dev) or disable delivery rather than drop mail silently."
            )
        # Live-AI boot preflight (D-026): refuse to start in live mode unless a
        # real provider call would actually succeed, rather than degrade to a
        # 500/404 on the first Run-AI. Fixture mode is unaffected.
        if self.shield_llm_mode == "live":
            ready, detail = self.live_llm_readiness()
            if not ready:
                raise RuntimeError(f"SHIELD_LLM_MODE=live is not runnable: {detail}")
        # Hybrid OIDC boot preflight (D-032), mirroring the live-AI gate: refuse
        # to start with the flag on but an incoherent Keycloak config, rather than
        # 500/503 on the first exchange. Config-shape only, no network (the api
        # has no depends_on: keycloak). Flag off is a full no-op.
        if self.shield_auth_oidc_enabled:
            ready, detail = self.oidc_readiness()
            if not ready:
                raise RuntimeError(f"SHIELD_AUTH_OIDC_ENABLED=true is not runnable: {detail}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

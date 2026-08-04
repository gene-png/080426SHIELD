"""Fixed-window rate limiting (Sprint 3 T3).

Two surfaces are protected:

  - **Auth** (`/auth/login`, `/auth/register`): per-IP + per-account fixed
    windows, checked *before* the expensive Argon2 work so a flood is cheap to
    reject and account-lockout stays a second line of defence.
  - **Run-AI** (the five expensive LLM-egress endpoints): a per-client window,
    so one tenant cannot exhaust the shared AI budget.

Counters live in Redis (composed, previously idle — D-015 Part F). The window
is a plain fixed window: ``INCR`` the key and arm the TTL, both in one atomic
MULTI/EXEC. ``EXPIRE ... NX`` sets the TTL only when the key has none, so the
first hit fixes the window and later hits leave it untouched.

FAIL-OPEN, loudly: if Redis is unreachable the request is ALLOWED and a warning
is logged. An infra blip must never brick authentication. Every other failure
mode (over the limit) FAILS LOUD with a typed 429 (D-016) carrying ``Retry-After``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings
from app.dependencies import current_client
from app.logging import get_logger
from app.models.client import Client

log = get_logger("app.security.rate_limit")


class RateLimitBackendError(RuntimeError):
    """The counter store (Redis) could not be reached or updated.

    Raised by a backend so the limiter can distinguish an infra outage (fail
    open) from a genuine over-limit condition (fail loud).
    """


@dataclass(frozen=True)
class RateLimit:
    """A fixed-window budget: at most ``limit`` events per ``window_seconds``."""

    limit: int
    window_seconds: int


class RateLimitBackend(Protocol):
    def incr(self, key: str, window_seconds: int) -> int:
        """Increment the window counter for ``key`` and return the new count.

        Must raise :class:`RateLimitBackendError` on any store failure so the
        limiter fails open rather than mistaking an outage for a violation.
        """
        ...


class RedisRateLimitBackend:
    """Fixed-window counter backed by Redis INCR + EXPIRE."""

    def __init__(self, client: object) -> None:
        self._client = client

    def incr(self, key: str, window_seconds: int) -> int:
        # Import lazily so the module (and the whole app) imports fine even if
        # the redis client isn't installed in a given environment.
        import redis

        try:
            # INCR and the TTL arm run in ONE MULTI/EXEC transaction: a mid-call
            # outage can never leave a key counting up forever with no expiry
            # (which would be a permanent lockout — the opposite of fail-open).
            # EXPIRE ... NX only arms the TTL when the key has none, so the
            # first hit sets the fixed window and later hits leave it untouched
            # (and a key that somehow lost its TTL self-heals on the next hit).
            pipe = self._client.pipeline(transaction=True)
            pipe.incr(key)
            pipe.expire(key, window_seconds, nx=True)
            count, _armed = pipe.execute()
            return int(count)
        except redis.RedisError as exc:  # pragma: no cover - exercised via fake in tests
            raise RateLimitBackendError(str(exc)) from exc


class RateLimiter:
    """Enforces the configured windows against an injected backend.

    ``settings`` is optional so the core :meth:`check` can be unit-tested with
    an explicit :class:`RateLimit`; the ``enforce_*`` convenience methods read
    their budgets from settings.
    """

    def __init__(self, backend: RateLimitBackend, settings: Settings | None = None) -> None:
        self._backend = backend
        self._settings = settings or get_settings()

    def check(self, key: str, rate: RateLimit) -> None:
        """Count one event against ``key``; raise typed 429 if over ``rate``.

        On a backend outage, log loudly and return (fail open).
        """
        try:
            count = self._backend.incr(key, rate.window_seconds)
        except RateLimitBackendError as exc:
            log.warning("rate_limit.backend_unavailable", key=key, error=str(exc))
            return
        if count > rate.limit:
            log.warning(
                "rate_limit.exceeded",
                key=key,
                count=count,
                limit=rate.limit,
                window_seconds=rate.window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "reason": "rate_limited",
                    "message": "Too many requests. Please slow down and try again shortly.",
                },
                headers={"Retry-After": str(rate.window_seconds)},
            )
        log.debug("rate_limit.ok", key=key, count=count, limit=rate.limit)

    # -- convenience enforcers -------------------------------------------------

    def enforce_auth(self, request: Request, email: str) -> None:
        """Per-IP + per-account limits for the auth endpoints."""
        if not self._settings.shield_rate_limit_enabled:
            return
        ip = request.client.host if request.client else "unknown"
        self.check(
            f"rl:auth:ip:{ip}",
            RateLimit(
                self._settings.shield_rate_limit_auth_ip_max,
                self._settings.shield_rate_limit_auth_ip_window_seconds,
            ),
        )
        self.check(
            f"rl:auth:acct:{email}",
            RateLimit(
                self._settings.shield_rate_limit_auth_account_max,
                self._settings.shield_rate_limit_auth_account_window_seconds,
            ),
        )

    def enforce_ai(self, client_id: uuid.UUID) -> None:
        """Per-client limit for the expensive run-AI endpoints."""
        if not self._settings.shield_rate_limit_enabled:
            return
        self.check(
            f"rl:ai:client:{client_id}",
            RateLimit(
                self._settings.shield_rate_limit_ai_max,
                self._settings.shield_rate_limit_ai_window_seconds,
            ),
        )


@lru_cache(maxsize=1)
def _redis_client() -> object:
    """Lazily construct a shared Redis client. Connection is deferred to first
    command, so this never fails at construction — the fail-open path in
    :meth:`RateLimiter.check` handles an unreachable server."""
    import redis

    return redis.Redis.from_url(get_settings().redis_url)


def get_rate_limiter() -> RateLimiter:
    """FastAPI dependency: the process-wide, Redis-backed limiter.

    Overridden in tests via ``app.dependency_overrides`` with a fake-backed
    limiter, so the suite runs with no Redis.
    """
    return RateLimiter(RedisRateLimitBackend(_redis_client()), get_settings())


def enforce_ai_rate_limit(
    client: Client = Depends(current_client),  # noqa: B008 - FastAPI DI idiom
    limiter: RateLimiter = Depends(get_rate_limiter),  # noqa: B008 - FastAPI DI idiom
) -> None:
    """Dependency for the run-AI routes: throttle per resolved tenant.

    Depends on the same ``current_client`` the route already uses (FastAPI
    dedups it within a request), so the key is exactly the resolved tenant id
    — no header re-parsing, no drift from the tenant the request operates on.
    """
    limiter.enforce_ai(client.id)

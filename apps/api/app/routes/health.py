"""Liveness + readiness endpoints.

`/health` is the liveness probe (process is up) — cheap, dependency-free.
`/ready` is the readiness probe: it reports a per-dependency matrix (db,
redis, minio, keycloak, LLM) and flips `ready=false` naming the offender when
any *required* dependency is down. Load balancers may point at either;
orchestrators (k8s) use both.

Design (Sprint 6 T3): db, redis, and minio are required — a down one makes the
process unable to serve real traffic, so it flips readiness. Keycloak is
dormant in v1 (custom-JWT auth) and LLM in fixture mode is a fully valid
running state, so both are informational (`required=false`) and never gate
readiness. Probes never raise: they catch and report a `down` status so the
endpoint always returns 200 with the offender named rather than a 500 that
hides which dependency broke. Each probe is a module-level function so tests
can simulate a down dependency by monkeypatching it.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.config import Settings, get_settings
from app.db.session import get_db
from app.logging import get_logger
from app.security.jwt import TokenError, verify_token

log = get_logger("app.routes.health")

# /ready is public (load balancers and k8s probe it unauthenticated), so the
# per-dependency `detail` — which carries exception types/messages and the LLM
# config state — is reduced to a generic per-status string for anonymous
# callers (Sprint 6 T10). The offender NAMES and each status are still exposed
# (operators and orchestrators need them); only the internal detail is withheld.
_REDACTED_DETAIL = {
    "ok": "ok",
    "down": "unavailable",
    "dormant": "dormant",
}

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str


class DependencyStatus(BaseModel):
    """One row of the readiness matrix.

    `status` is "ok", "down", or "dormant". `required` marks whether a non-ok
    status flips overall readiness. `detail` is a human string for operators.
    """

    status: str
    required: bool
    detail: str


class ReadyResponse(BaseModel):
    status: str  # "ok" | "degraded"
    ready: bool
    version: str
    checks: dict[str, DependencyStatus]
    offenders: list[str]  # required deps that are not "ok", named


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


# -- per-dependency probes (module-level so tests can monkeypatch them) --------


def _probe_db(db: Session) -> DependencyStatus:
    try:
        db.execute(text("SELECT 1"))
        return DependencyStatus(status="ok", required=True, detail="SELECT 1 ok")
    except Exception as exc:  # noqa: BLE001 - readiness reports, never raises
        return DependencyStatus(status="down", required=True, detail=f"{type(exc).__name__}: {exc}")


def _probe_redis(settings: Settings) -> DependencyStatus:
    try:
        import redis

        client = redis.Redis.from_url(
            settings.redis_url, socket_connect_timeout=2, socket_timeout=2
        )
        client.ping()
        return DependencyStatus(status="ok", required=True, detail="PING ok")
    except Exception as exc:  # noqa: BLE001 - readiness reports, never raises
        return DependencyStatus(status="down", required=True, detail=f"{type(exc).__name__}: {exc}")


def _probe_minio(settings: Settings) -> DependencyStatus:  # noqa: ARG001 - kept uniform
    try:
        from app.storage.factory import get_storage

        get_storage().health_check()
        return DependencyStatus(status="ok", required=True, detail="bucket reachable")
    except Exception as exc:  # noqa: BLE001 - readiness reports, never raises
        return DependencyStatus(status="down", required=True, detail=f"{type(exc).__name__}: {exc}")


_KEYCLOAK_PROBE_TIMEOUT_SECONDS = 2.0


def _probe_keycloak(settings: Settings) -> DependencyStatus:
    # Hybrid OIDC via Keycloak is flag-gated (D-032, SHIELD_AUTH_OIDC_ENABLED).
    # OFF (the dev/e2e default) -> `dormant`, no network, exactly as v1 — but the
    # detail now NAMES the flag so an operator knows what to flip. ON -> a REAL
    # probe of the JWKS endpoint (httpx GET, 2s timeout) reporting `ok`/`down`.
    # Either way `required=False`: credentials login keeps the app serviceable
    # during a Keycloak outage, so OIDC must NEVER gate LB readiness.
    if not settings.shield_auth_oidc_enabled:
        return DependencyStatus(
            status="dormant",
            required=False,
            detail="Keycloak OIDC is dormant (SHIELD_AUTH_OIDC_ENABLED is off); not probed.",
        )
    try:
        resp = httpx.get(settings.keycloak_jwks_url, timeout=_KEYCLOAK_PROBE_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return DependencyStatus(
            status="ok",
            required=False,
            detail=f"JWKS reachable at {settings.keycloak_jwks_url}",
        )
    except Exception as exc:  # noqa: BLE001 - readiness reports, never raises
        return DependencyStatus(
            status="down", required=False, detail=f"{type(exc).__name__}: {exc}"
        )


def _probe_llm(settings: Settings) -> DependencyStatus:
    # Fixture mode is a fully valid running state (deterministic offline
    # suggestions), so LLM readiness is informational and never gates /ready.
    # In live mode the boot preflight (D-026) already refuses to start unless a
    # real call would succeed, so a running live process is ready by
    # construction; we still surface the detail for the operator view.
    if settings.shield_llm_mode != "live":
        return DependencyStatus(
            status="ok",
            required=False,
            detail="fixture mode (AI suggestions are deterministic offline)",
        )
    ready, detail = settings.live_llm_readiness()
    return DependencyStatus(status="ok" if ready else "down", required=False, detail=detail)


def _caller_is_authenticated(request: Request) -> bool:
    """True when the request carries a structurally valid, unexpired access
    token. Token-signature only (no DB load) so /ready stays cheap — the gated
    payload is diagnostic operator detail, not user data. Anonymous callers get
    the reduced matrix; authenticated callers get full detail."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return False
    token = auth.split(" ", 1)[1].strip()
    try:
        verify_token(token, expected_type="access")
    except TokenError:
        return False
    return True


def _redacted(check: DependencyStatus) -> DependencyStatus:
    return DependencyStatus(
        status=check.status,
        required=check.required,
        detail=_REDACTED_DETAIL.get(check.status, check.status),
    )


@router.get(
    "/ready",
    response_model=ReadyResponse,
    summary="Readiness probe (per-dependency matrix)",
)
def ready(
    request: Request,
    db: Session = Depends(get_db),  # noqa: B008 - FastAPI DI idiom
) -> ReadyResponse:
    settings = get_settings()
    checks: dict[str, DependencyStatus] = {
        "db": _probe_db(db),
        "redis": _probe_redis(settings),
        "minio": _probe_minio(settings),
        "keycloak": _probe_keycloak(settings),
        "llm": _probe_llm(settings),
    }
    offenders = [name for name, c in checks.items() if c.required and c.status != "ok"]
    is_ready = not offenders
    if is_ready:
        log.debug("ready.ok", checks={n: c.status for n, c in checks.items()})
    else:
        log.warning("ready.degraded", offenders=offenders)

    # Withhold internal detail from anonymous callers (offenders + statuses stay).
    if not _caller_is_authenticated(request):
        checks = {name: _redacted(c) for name, c in checks.items()}

    return ReadyResponse(
        status="ok" if is_ready else "degraded",
        ready=is_ready,
        version=__version__,
        checks=checks,
        offenders=offenders,
    )

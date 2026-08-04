"""Rate-limiting tests (Sprint 3 T3).

Fixed-window per-IP + per-account limits on auth; per-client limits on the
expensive run-AI path. Redis-backed in prod; here we drive the limiter with a
fake in-memory backend and a broken backend so the whole surface is exercised
offline (tests run SQLite / no Redis):

  - a counter over its window -> typed 429 reason=rate_limited + Retry-After;
  - a Redis outage (backend raises) -> request ALLOWED (fail-open) + a loud
    structlog warning, so an infra blip never bricks auth;
  - the wiring on /auth/login enforces both the per-IP and per-account buckets
    with the D-016 typed envelope and the Retry-After header actually reaching
    the client.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# -----------------------------------------------------------------------------
# Fakes
# -----------------------------------------------------------------------------


class _FakeBackend:
    """In-memory fixed-window counter — stands in for Redis in tests."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    def incr(self, key: str, window_seconds: int) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        self.expires[key] = window_seconds
        return self.counts[key]


class _BrokenBackend:
    """A backend whose every call fails the way a Redis outage would."""

    def incr(self, key: str, window_seconds: int) -> int:
        from app.security.rate_limit import RateLimitBackendError

        raise RateLimitBackendError("redis is down")


class _FakePipeline:
    """Models a redis-py MULTI/EXEC pipeline over the shared store."""

    def __init__(self, store: dict[str, int], ttls: dict[str, int]) -> None:
        self._store = store
        self._ttls = ttls
        self._ops: list[tuple] = []

    def incr(self, key: str) -> _FakePipeline:
        self._ops.append(("incr", key))
        return self

    def expire(self, key: str, seconds: int, nx: bool = False) -> _FakePipeline:
        self._ops.append(("expire", key, seconds, nx))
        return self

    def execute(self) -> list:
        results: list = []
        for op in self._ops:
            if op[0] == "incr":
                self._store[op[1]] = self._store.get(op[1], 0) + 1
                results.append(self._store[op[1]])
            else:
                _, key, seconds, nx = op
                if nx and key in self._ttls:
                    results.append(False)  # NX: TTL already set, leave it
                else:
                    self._ttls[key] = seconds
                    results.append(True)
        return results


class _FakeRedis:
    """A minimal Redis stand-in that ONLY exposes the atomic pipeline path.

    Standalone ``incr``/``expire`` raise, so any non-atomic INCR-then-EXPIRE
    implementation fails this fake — the counter and its TTL must be armed in a
    single MULTI/EXEC so a mid-call outage can never leave a key incrementing
    forever without an expiry (the fail-open promise).
    """

    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        return _FakePipeline(self.store, self.ttls)

    def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)

    def incr(self, key: str) -> int:  # pragma: no cover - guard
        raise AssertionError("must arm counter + TTL atomically via pipeline, not standalone incr")

    def expire(self, key: str, seconds: int, nx: bool = False) -> bool:  # pragma: no cover - guard
        raise AssertionError("must arm TTL atomically via pipeline, not a standalone expire")


# -----------------------------------------------------------------------------
# Core limiter behaviour
# -----------------------------------------------------------------------------


@pytest.mark.unit
def test_check_allows_up_to_limit_then_raises_typed_429() -> None:
    from fastapi import HTTPException

    from app.security.rate_limit import RateLimit, RateLimiter

    limiter = RateLimiter(_FakeBackend())
    rate = RateLimit(limit=3, window_seconds=60)

    # First `limit` calls pass silently.
    for _ in range(3):
        limiter.check("k", rate)

    # The one over the line raises a typed 429 with a Retry-After hint.
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("k", rate)
    exc = exc_info.value
    assert exc.status_code == 429
    assert exc.detail["reason"] == "rate_limited"
    assert exc.headers["Retry-After"] == "60"


@pytest.mark.unit
def test_distinct_keys_have_independent_windows() -> None:
    from app.security.rate_limit import RateLimit, RateLimiter

    limiter = RateLimiter(_FakeBackend())
    rate = RateLimit(limit=1, window_seconds=60)

    limiter.check("a", rate)  # consumes a's budget
    limiter.check("b", rate)  # b is independent, still fine


@pytest.mark.unit
def test_fail_open_when_backend_unavailable(capsys) -> None:
    """A Redis outage must never block a request — allow it, loudly.

    structlog renders to stdout via PrintLoggerFactory, so we capture stdout
    (not stdlib caplog) to prove the warning is emitted.
    """
    from app.security.rate_limit import RateLimit, RateLimiter

    limiter = RateLimiter(_BrokenBackend())
    rate = RateLimit(limit=1, window_seconds=60)

    # Far more calls than the limit; none may raise because the backend is
    # down and we fail open.
    for _ in range(5):
        limiter.check("k", rate)

    assert "rate_limit.backend_unavailable" in capsys.readouterr().out


@pytest.mark.unit
def test_redis_backend_arms_ttl_atomically_with_the_counter() -> None:
    """The counter and its TTL are set in one atomic op, TTL armed only once.

    A non-atomic INCR-then-EXPIRE could crash between the two calls and leave a
    key counting up forever with no expiry — a permanent lockout that violates
    the module's fail-open promise. The window TTL must also survive subsequent
    hits (fixed window), not reset on every request.
    """
    from app.security.rate_limit import RedisRateLimitBackend

    fake = _FakeRedis()
    backend = RedisRateLimitBackend(fake)

    assert backend.incr("k", 60) == 1
    assert fake.ttl("k") == 60  # TTL armed alongside the very first count

    assert backend.incr("k", 60) == 2
    assert fake.ttl("k") == 60  # fixed window preserved — NX kept the original


@pytest.mark.unit
def test_enforce_ai_blocks_per_client_after_limit() -> None:
    import uuid

    from fastapi import HTTPException

    from app.config import Settings
    from app.security.rate_limit import RateLimiter

    settings = Settings(shield_rate_limit_ai_max=2, shield_rate_limit_ai_window_seconds=60)
    limiter = RateLimiter(_FakeBackend(), settings)
    cid = uuid.uuid4()

    limiter.enforce_ai(cid)
    limiter.enforce_ai(cid)
    with pytest.raises(HTTPException) as exc_info:
        limiter.enforce_ai(cid)
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["reason"] == "rate_limited"


@pytest.mark.unit
def test_enforce_ai_rate_limit_dependency_yields_typed_429() -> None:
    """The dependency wired onto the run-AI routes (csf/zt/attack/tech_debt)
    throttles per resolved tenant and raises the D-016 typed 429 over limit."""
    import uuid
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.config import Settings
    from app.security.rate_limit import RateLimiter, enforce_ai_rate_limit

    settings = Settings(shield_rate_limit_ai_max=1, shield_rate_limit_ai_window_seconds=60)
    limiter = RateLimiter(_FakeBackend(), settings)
    client = SimpleNamespace(id=uuid.uuid4())

    enforce_ai_rate_limit(client=client, limiter=limiter)  # first call within budget
    with pytest.raises(HTTPException) as exc_info:
        enforce_ai_rate_limit(client=client, limiter=limiter)
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["reason"] == "rate_limited"
    assert exc_info.value.headers["Retry-After"] == "60"


@pytest.mark.unit
def test_disabled_limiter_never_blocks() -> None:
    import uuid

    from app.config import Settings
    from app.security.rate_limit import RateLimiter

    settings = Settings(shield_rate_limit_enabled=False, shield_rate_limit_ai_max=1)
    limiter = RateLimiter(_FakeBackend(), settings)
    cid = uuid.uuid4()
    for _ in range(5):
        limiter.enforce_ai(cid)  # never raises when the feature is off


# -----------------------------------------------------------------------------
# Route wiring: /auth/login enforces both buckets, typed envelope, Retry-After
# -----------------------------------------------------------------------------


def _make_app_client(settings) -> Iterator[TestClient]:
    from app.db.session import get_db
    from app.main import create_app
    from app.security.rate_limit import RateLimiter, get_rate_limiter

    def override_get_db() -> Iterator[Session]:
        db = _make_app_client._TestSession()
        try:
            yield db
        finally:
            db.close()

    limiter = RateLimiter(_FakeBackend(), settings)

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sqlite_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'shield-rl.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    _make_app_client._TestSession = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    return engine


@pytest.mark.unit
def test_login_per_ip_rate_limited(sqlite_engine) -> None:
    from app.config import Settings

    settings = Settings(
        shield_rate_limit_auth_ip_max=3,
        shield_rate_limit_auth_ip_window_seconds=60,
        shield_rate_limit_auth_account_max=100,
        shield_rate_limit_auth_account_window_seconds=60,
    )
    client = next(_make_app_client(settings))

    body = {"email": "nobody@example.com", "password": "whatever-wrong-pass!"}
    # First 3 attempts hit the auth logic (401 invalid credentials).
    for _ in range(3):
        r = client.post("/auth/login", json=body)
        assert r.status_code == 401, r.text
    # The 4th trips the per-IP limit before any auth work.
    r = client.post("/auth/login", json=body)
    assert r.status_code == 429, r.text
    assert r.json()["error"]["reason"] == "rate_limited"
    assert r.headers["retry-after"] == "60"


@pytest.mark.unit
def test_login_per_account_rate_limited(sqlite_engine) -> None:
    from app.config import Settings

    settings = Settings(
        shield_rate_limit_auth_ip_max=100,
        shield_rate_limit_auth_ip_window_seconds=60,
        shield_rate_limit_auth_account_max=2,
        shield_rate_limit_auth_account_window_seconds=60,
    )
    client = next(_make_app_client(settings))

    victim = {"email": "victim@example.com", "password": "wrong-pass-guess!"}
    for _ in range(2):
        r = client.post("/auth/login", json=victim)
        assert r.status_code == 401, r.text
    # Third attempt on the same account trips the per-account bucket.
    r = client.post("/auth/login", json=victim)
    assert r.status_code == 429, r.text

    # A different account is unaffected (per-account keying, not global).
    r = client.post("/auth/login", json={"email": "other@example.com", "password": "x!"})
    assert r.status_code == 401, r.text

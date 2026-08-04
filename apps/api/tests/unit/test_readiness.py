"""Full dependency-health readiness endpoint (Sprint 6 T3).

`/ready` reports a per-dependency matrix — db, redis, minio, keycloak
(dormant), and LLM readiness. A down *required* dependency flips
`ready=false` and names the offender; informational checks (keycloak,
llm-in-fixture) never gate readiness. `/health` stays cheap.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def ready_client(monkeypatch) -> Iterator[TestClient]:
    """App whose db probe hits a live in-memory SQLite (SELECT 1 works) and
    whose external-service probes are monkeypatchable per test."""
    import app.routes.health as health_mod
    from app.db.session import get_db
    from app.main import create_app

    engine = create_engine("sqlite://", future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    # Default the network probes to healthy so a test that wants an all-green
    # matrix doesn't need a real Redis/MinIO. Individual tests override these.
    monkeypatch.setattr(
        health_mod,
        "_probe_redis",
        lambda settings: health_mod.DependencyStatus(status="ok", required=True, detail="PING ok"),
    )
    monkeypatch.setattr(
        health_mod,
        "_probe_minio",
        lambda settings: health_mod.DependencyStatus(
            status="ok", required=True, detail="bucket reachable"
        ),
    )

    with TestClient(app) as c:
        yield c


@pytest.mark.unit
def test_health_liveness_does_not_touch_dependencies(ready_client: TestClient) -> None:
    # Liveness must stay cheap: no checks matrix, always ok.
    body = ready_client.get("/health").json()
    assert body["status"] == "ok"
    assert "checks" not in body


@pytest.mark.unit
def test_ready_reports_full_dependency_matrix(ready_client: TestClient) -> None:
    resp = ready_client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["status"] == "ok"
    checks = body["checks"]
    for dep in ("db", "redis", "minio", "keycloak", "llm"):
        assert dep in checks, f"{dep} missing from readiness matrix"
        assert "status" in checks[dep]
        assert "required" in checks[dep]
    assert checks["db"]["status"] == "ok"


@pytest.mark.unit
def test_ready_marks_keycloak_dormant_and_not_required(ready_client: TestClient) -> None:
    # Default dev/e2e stack keeps SHIELD_AUTH_OIDC_ENABLED off (D-032), so the
    # keycloak probe reports `dormant` and never gates readiness.
    checks = ready_client.get("/ready").json()["checks"]
    assert checks["keycloak"]["status"] == "dormant"
    assert checks["keycloak"]["required"] is False


@pytest.mark.unit
def test_ready_llm_fixture_mode_ok_and_informational(ready_client: TestClient) -> None:
    # Fixture mode is a valid running state, so LLM must not gate readiness.
    checks = ready_client.get("/ready").json()["checks"]
    assert checks["llm"]["required"] is False
    assert checks["llm"]["status"] == "ok"


@pytest.mark.unit
def test_ready_flips_false_and_names_offender_when_redis_down(
    ready_client: TestClient, monkeypatch
) -> None:
    import app.routes.health as health_mod

    monkeypatch.setattr(
        health_mod,
        "_probe_redis",
        lambda settings: health_mod.DependencyStatus(
            status="down", required=True, detail="ConnectionError: refused"
        ),
    )
    body = ready_client.get("/ready").json()
    assert body["ready"] is False
    assert body["status"] == "degraded"
    assert body["checks"]["redis"]["status"] == "down"
    # The offender is named in the response.
    assert "redis" in body["offenders"]
    assert "db" not in body["offenders"]


@pytest.mark.unit
def test_ready_flips_false_when_minio_down(ready_client: TestClient, monkeypatch) -> None:
    import app.routes.health as health_mod

    monkeypatch.setattr(
        health_mod,
        "_probe_minio",
        lambda settings: health_mod.DependencyStatus(
            status="down", required=True, detail="EndpointConnectionError"
        ),
    )
    body = ready_client.get("/ready").json()
    assert body["ready"] is False
    assert "minio" in body["offenders"]


@pytest.mark.unit
def test_ready_stays_true_when_only_informational_check_off(
    ready_client: TestClient, monkeypatch
) -> None:
    # An informational (not-required) check being non-ok must NOT flip readiness.
    import app.routes.health as health_mod

    monkeypatch.setattr(
        health_mod,
        "_probe_llm",
        lambda settings: health_mod.DependencyStatus(
            status="down", required=False, detail="live mode misconfigured"
        ),
    )
    body = ready_client.get("/ready").json()
    assert body["ready"] is True
    assert body["offenders"] == []


@pytest.mark.unit
def test_ready_redacts_detail_for_anonymous_callers(ready_client: TestClient, monkeypatch) -> None:
    # /ready is public (LBs/k8s hit it unauthenticated). It must still name the
    # offender and report each status, but NOT leak internal exception detail or
    # LLM config state to anonymous callers (Sprint 6 T10).
    import app.routes.health as health_mod

    monkeypatch.setattr(
        health_mod,
        "_probe_redis",
        lambda settings: health_mod.DependencyStatus(
            status="down",
            required=True,
            detail="ConnectionError: refused to redis://secret-internal-host:6379",
        ),
    )
    body = ready_client.get("/ready").json()

    # Operator-actionable signal is preserved.
    assert body["ready"] is False
    assert "redis" in body["offenders"]
    assert body["checks"]["redis"]["status"] == "down"

    # Internal exception detail is NOT exposed to anonymous callers.
    for check in body["checks"].values():
        assert "ConnectionError" not in check["detail"]
        assert "secret-internal-host" not in check["detail"]
    # LLM config state is likewise not disclosed.
    assert "fixture" not in body["checks"]["llm"]["detail"].lower()


@pytest.mark.unit
def test_ready_full_detail_for_authenticated_caller(ready_client: TestClient, monkeypatch) -> None:
    # An authenticated caller (valid access token) DOES get the full operator
    # detail — the reduction only applies to anonymous callers.
    import uuid

    import app.routes.health as health_mod
    from app.security.jwt import issue_token

    monkeypatch.setattr(
        health_mod,
        "_probe_redis",
        lambda settings: health_mod.DependencyStatus(
            status="down",
            required=True,
            detail="ConnectionError: refused to redis://secret-internal-host:6379",
        ),
    )
    token, _payload = issue_token(subject=uuid.uuid4(), role="admin", typ="access")
    body = ready_client.get("/ready", headers={"Authorization": f"Bearer {token}"}).json()

    assert "ConnectionError" in body["checks"]["redis"]["detail"]
    assert "secret-internal-host" in body["checks"]["redis"]["detail"]


@pytest.mark.unit
def test_probe_redis_reports_down_on_unreachable_server() -> None:
    # Real probe against a dead address fails loudly-but-caught into a "down"
    # status (readiness must never raise 500 — it reports the offender).
    from app.config import Settings
    from app.routes.health import _probe_redis

    settings = Settings(redis_url="redis://127.0.0.1:1/0")
    result = _probe_redis(settings)
    assert result.status == "down"
    assert result.required is True
    assert result.detail


# -- keycloak probe: flag-gated dual-horizon behavior (Sprint 9 T5, D-032) -----


@pytest.mark.unit
def test_probe_keycloak_dormant_when_flag_off() -> None:
    # OIDC flag off (the dev/e2e default): no network, `dormant`, and the detail
    # NAMES the flag so an operator knows exactly what to flip.
    from app.config import Settings
    from app.routes.health import _probe_keycloak

    result = _probe_keycloak(Settings(shield_auth_oidc_enabled=False))
    assert result.status == "dormant"
    assert result.required is False
    assert "SHIELD_AUTH_OIDC_ENABLED" in result.detail


@pytest.mark.unit
def test_probe_keycloak_ok_when_flag_on_and_jwks_reachable(monkeypatch) -> None:
    # Flag on + a reachable JWKS endpoint -> `ok`, still informational.
    import app.routes.health as health_mod
    from app.config import Settings

    class _Resp:
        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(health_mod.httpx, "get", lambda url, timeout: _Resp())
    result = health_mod._probe_keycloak(Settings(shield_auth_oidc_enabled=True))
    assert result.status == "ok"
    assert result.required is False


@pytest.mark.unit
def test_probe_keycloak_down_when_flag_on_and_jwks_unreachable(monkeypatch) -> None:
    # Flag on but the fetch raises -> `down`, but NEVER required: a Keycloak
    # outage must not flip readiness (credentials login keeps the app usable).
    import app.routes.health as health_mod
    from app.config import Settings

    def _boom(url, timeout):  # noqa: ANN001, ANN202
        raise health_mod.httpx.ConnectError("connection refused")

    monkeypatch.setattr(health_mod.httpx, "get", _boom)
    result = health_mod._probe_keycloak(Settings(shield_auth_oidc_enabled=True))
    assert result.status == "down"
    assert result.required is False
    assert result.detail


@pytest.mark.unit
def test_ready_stays_true_when_keycloak_down_with_flag_on(
    ready_client: TestClient, monkeypatch
) -> None:
    # The load-bearing contract: even a DOWN keycloak (flag on) leaves overall
    # readiness true and does not name keycloak as an offender.
    import app.routes.health as health_mod

    monkeypatch.setattr(
        health_mod,
        "_probe_keycloak",
        lambda settings: health_mod.DependencyStatus(
            status="down", required=False, detail="ConnectError: connection refused"
        ),
    )
    body = ready_client.get("/ready").json()
    assert body["ready"] is True
    assert body["status"] == "ok"
    assert body["checks"]["keycloak"]["status"] == "down"
    assert "keycloak" not in body["offenders"]

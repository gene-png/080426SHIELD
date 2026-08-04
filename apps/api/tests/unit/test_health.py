"""Smoke tests for /health and correlation-ID middleware."""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_health_returns_ok(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


@pytest.mark.unit
def test_health_emits_correlation_id_header(client) -> None:
    response = client.get("/health")
    cid = response.headers.get("X-Request-ID")
    assert cid, "every response must carry an X-Request-ID header"
    assert 0 < len(cid) <= 128


@pytest.mark.unit
def test_health_echoes_inbound_correlation_id(client) -> None:
    response = client.get("/health", headers={"X-Request-ID": "test-trace-abc-123"})
    assert response.headers["X-Request-ID"] == "test-trace-abc-123"


@pytest.mark.unit
def test_health_rejects_malformed_inbound_correlation_id(client) -> None:
    response = client.get("/health", headers={"X-Request-ID": "has spaces and / slashes"})
    cid = response.headers["X-Request-ID"]
    assert cid != "has spaces and / slashes"
    assert cid

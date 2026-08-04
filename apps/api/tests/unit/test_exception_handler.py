"""Verify that unhandled exceptions return correlation-ID-only 500s.

AI Prompt §4.4 + Master Spec §6.3: stack traces must NEVER leak.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def app_with_boom():
    app = create_app()

    @app.get("/_boom")
    def boom() -> None:
        raise RuntimeError("internal secret value that must not leak")

    @app.get("/_teapot")
    def teapot() -> None:
        raise HTTPException(status_code=418, detail="I'm a teapot")

    return app


@pytest.mark.unit
def test_unhandled_exception_returns_500_without_stack_trace(app_with_boom) -> None:
    with TestClient(app_with_boom, raise_server_exceptions=False) as c:
        response = c.get("/_boom")
    assert response.status_code == 500
    body = response.text
    assert "RuntimeError" not in body
    assert "internal secret value" not in body
    payload = response.json()
    assert payload["error"]["code"] == 500
    assert payload["error"]["correlation_id"]
    assert "Traceback" not in body


@pytest.mark.unit
def test_http_exception_preserves_status_and_detail(app_with_boom) -> None:
    with TestClient(app_with_boom) as c:
        response = c.get("/_teapot")
    assert response.status_code == 418
    payload = response.json()
    assert payload["error"]["code"] == 418
    assert payload["error"]["message"] == "I'm a teapot"
    assert payload["error"]["correlation_id"]

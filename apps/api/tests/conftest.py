"""Test fixtures."""

from __future__ import annotations

import os

import pytest

# Keep tests fully offline: no DB, no Redis, no LLM. Routes that need those
# will set up their own ephemeral resources in later stages.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SHIELD_LLM_MODE", "fixture")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c

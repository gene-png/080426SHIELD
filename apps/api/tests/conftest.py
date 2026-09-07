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


# Keep pytest out of the gate fixtures: they are INPUTS, not tests.
#
# `testpaths = ["tests"]`, so a bare `pytest` from apps/api walks tests/gates.
# Two fixtures are named `test_*.py` because the gate they exercise
# (`check_test_integrity`) only looks at that pattern -- renaming them would make
# them invisible to the thing they test. One imports a symbol that does not
# exist, deliberately: it is a verbatim reproduction of the #72 instance, kept so
# `check_gate_fixtures.py` can assert the gate exits 1 on it. Collecting them
# fails for a reason unrelated to whatever the developer was doing.
#
# This lives HERE rather than in tests/gates/conftest.py because that directory
# is excluded from ruff and black -- a conftest there is real code going unlinted,
# which is an exclusion wider than its own justification ("files that are data").
#
# LOAD-BEARING ON THE HARNESS RUNNING, like the ruff/black/prettier/test-integrity
# exclusions: if the "gates can fail" step goes away, this goes with it.
#
# CI is unaffected either way -- it runs `pytest -m unit tests/unit`.
collect_ignore_glob = ["gates/*"]

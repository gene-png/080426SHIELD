"""Contract: the csf_score PROMPT schema must match the run_ai PARSER (Sprint 3 T0).

The audit find that motivated this: ``_CSF_SCORE_PROMPT`` documented a
``{"subcategories": [{"code": ...}]}`` response while ``routes/csf.py:run_ai``
parses ``{"scores": [{"tier", "subcategory_code", ...}]}`` — so live mode
silently discarded every schema-compliant response (a fail-loudly violation).

These tests lock the two together:

  * a static test asserts the prompt text documents exactly the keys the parser
    reads (and no longer documents the divergent legacy shape);
  * an end-to-end test feeds a response constructed to the prompt's documented
    schema and asserts the route applies changes (> 0) — it would fail if either
    side drifted again.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.jobs import _CSF_SCORE_PROMPT
from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.csf.catalog import SUBCATEGORIES
from app.routes.csf import _DIM_FIELDS

# The exact keys routes/csf.py:run_ai depends on when parsing the response.
_PARSER_TOP_LEVEL_KEY = "scores"
_PARSER_ROW_KEYS = ("tier", "subcategory_code", *_DIM_FIELDS, "what_we_found")


@pytest.mark.unit
def test_prompt_documents_exactly_the_parser_schema() -> None:
    """Prompt text must name every key the parser reads, and drop the old shape."""
    assert f'"{_PARSER_TOP_LEVEL_KEY}"' in _CSF_SCORE_PROMPT
    for key in _PARSER_ROW_KEYS:
        assert f'"{key}"' in _CSF_SCORE_PROMPT, f"prompt no longer documents {key!r}"
    # The legacy divergent shape (the actual bug) must be gone: the parser keys
    # rows on tier+subcategory_code, never a bare "code" under "subcategories".
    assert '"subcategories": [{"code"' not in _CSF_SCORE_PROMPT
    assert '"subcategories": [{ "code"' not in _CSF_SCORE_PROMPT


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, FixtureProvider]]:
    url = f"sqlite:///{tmp_path / 'shield-csfcontract.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app
    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain
    from app.routes.csf import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    provider = FixtureProvider()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    _seed = TestSession()
    tenant = _Client(legal_name="Test Tenant")
    _seed.add(tenant)
    _seed.flush()
    _seed.add(_ClientDomain(client_id=tenant.id, domain="example.com"))
    _seed.commit()
    with TestClient(app, headers={"X-Client-Id": str(tenant.id)}) as c:
        yield c, provider


def _bootstrap(c: TestClient) -> tuple[dict, str]:
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()[
        "id"
    ]
    c.post(f"/csf/services/{svc_id}/assessments", headers=h)
    c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    return h, svc_id


@pytest.mark.unit
def test_prompt_schema_response_applies_changes(app_client) -> None:
    """A response built to the prompt's documented schema must apply (changes > 0).

    Constructed from the same key constants the parser uses, so if prompt and
    parser diverge again this fails loudly instead of silently discarding.
    """
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    code = SUBCATEGORIES[0].code
    row = {"tier": "high", "subcategory_code": code, "what_we_found": "Grounded finding."}
    for i, dim in enumerate(_DIM_FIELDS):
        row[dim] = i % 3  # deterministic 0/1/2, on-schema
    body = {_PARSER_TOP_LEVEL_KEY: [row], "executive_summary": "Contract check."}
    provider.register_static("csf_score", LLMResponse(json.dumps(body)))

    r = c.post(f"/csf/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    changed = r.json()["changed"]
    assert len(changed) > 0, "a prompt-schema-compliant response was discarded"
    changed_fields = {ch["field"] for ch in changed if ch["subcategory_code"] == code}
    # Every non-zero dimension we sent should show up as an applied change.
    for i, dim in enumerate(_DIM_FIELDS):
        if i % 3:
            assert dim in changed_fields
    assert "what_we_found" in changed_fields

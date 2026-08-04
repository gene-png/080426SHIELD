"""Opt-in live-AI integration test (Sprint 6 T1 / T7, D-026).

These make a REAL provider call. They are marked ``@pytest.mark.live`` ONLY
(never ``unit``), so the default ``pytest -m unit`` gate deselects them and CI —
which runs ``pytest -m unit tests/unit`` — never even collects them (this module
lives outside ``tests/unit``). They self-skip unless ``SHIELD_LLM_MODE=live`` and
a runnable provider key are present, so a keyless loop/CI stays green.

Run them deliberately, with a key, from the api container:
  docker compose exec -T \
    -e SHIELD_LLM_MODE=live -e ANTHROPIC_API_KEY=sk-ant-... \
    api pytest -m live tests/live -q

T1 proved the ``csf_score`` purpose. T7 extends the same contract across ALL
FIVE AI purposes — ``csf_score``, ``zt_score``, ``mitre_map``,
``risk_synthesize``, ``tech_debt_extract`` — so a real key exercises every
adapter's response parse, not just CSF. Each case asserts the same contract the
manual 2026-07-12 smoke proved:

  * a real, completed ``llm_calls`` row (provider/model/mode=live/status=
    completed/tokens/duration, null ``error_message``);
  * redaction actually ran — every payload plants the SAME canonical PII twice
    each (org/name/email), so ``redacted_counts`` must equal
    ``{"email": 2, "name": 2, "client_org": 2}`` for every purpose;
  * NO raw PII survives into the model's response;
  * the response PARSES into the purpose's documented container (the same key
    the route layer reads) — this is the per-adapter parse check T7 exists for.

The canonical PII constants + the CSF builder are imported from
``scripts.smoke_live_ai`` so the automated and manual paths cannot drift; the
four additional purpose builders live here (T7's expected_paths cover
``apps/api/tests`` only) and reuse the same PII so counts stay uniform.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from scripts.smoke_live_ai import (
    CLIENT_ORG,
    CONTACT_EMAIL,
    CONTACT_NAME,
    EXPECTED_REDACTED_COUNTS,
    PII_STRINGS,
    build_csf_pii_inputs,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.engine import run_job
from app.ai.llm import LLMClient
from app.config import get_settings
from app.models.llm_call import LLMCallMode, LLMCallStatus
from app.models.user import User, UserRole
from app.tech_debt.extract import ExtractedCapability


def _live_ready() -> tuple[bool, str]:
    settings = get_settings()
    if settings.shield_llm_mode != "live":
        return False, "SHIELD_LLM_MODE is not 'live'"
    return settings.live_llm_readiness()


_READY, _WHY = _live_ready()

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not _READY, reason=f"live AI not configured: {_WHY}"),
]


@pytest.fixture()
def db_factory(tmp_path) -> Iterator[sessionmaker]:
    db_path = tmp_path / "shield-live.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _new_admin(db: Session) -> User:
    user = User(
        email="live-smoke@kentro.example",
        password_hash="x" * 64,
        role=UserRole.ADMIN,
        display_name="Live Smoke",
    )
    db.add(user)
    db.flush()
    return user


# --- Canonical PII notes, planted once per payload -------------------------
# One string carrying the client org twice, the contact name twice, and the
# contact email twice — so strict-mode redaction of any purpose that embeds it
# once yields EXACTLY {"email": 2, "name": 2, "client_org": 2}. Mirrors the CSF
# builder in scripts.smoke_live_ai (kept in lock-step via the shared constants)
# so every purpose exercises the identical redaction contract.
def _pii_notes() -> str:
    return (
        f"{CLIENT_ORG} governance is owned by {CONTACT_NAME}. Reach "
        f"{CONTACT_NAME} at {CONTACT_EMAIL} for the {CLIENT_ORG} "
        f"risk-council charter and supporting evidence ({CONTACT_EMAIL})."
    )


def _build_zt() -> tuple[dict, str, tuple[str, ...]]:
    inputs = {
        "framework": "cisa_ztmm",
        "capabilities": [{"code": "IDN-1", "current_answer": "partial", "notes": _pii_notes()}],
    }
    return inputs, CLIENT_ORG, (CONTACT_NAME,)


def _build_mitre() -> tuple[dict, str, tuple[str, ...]]:
    inputs = {
        "capabilities": [
            {"name": "Endpoint Detection", "vendor": "ExampleEDR", "notes": _pii_notes()}
        ],
        "context": {"engagement": "ATT&CK coverage review"},
    }
    return inputs, CLIENT_ORG, (CONTACT_NAME,)


def _build_risk() -> tuple[dict, str, tuple[str, ...]]:
    inputs = {
        "findings": [
            {
                "source": "coverage_finding",
                "source_id": "F-1",
                "summary": _pii_notes(),
                "linked_techniques": ["T1003"],
                "linked_controls": ["PR.AC-01"],
            }
        ],
    }
    return inputs, CLIENT_ORG, (CONTACT_NAME,)


def _build_tech_debt() -> tuple[dict, str, tuple[str, ...]]:
    inputs = {
        "rows": [
            {
                "tool": "Example SIEM",
                "owner_notes": _pii_notes(),
                "annual_cost_usd": 12000,
            }
        ],
        "context": {"source_filename": "inventory.csv", "source_mime": "text/csv"},
    }
    return inputs, CLIENT_ORG, (CONTACT_NAME,)


def _check_csf(data) -> None:
    assert isinstance(data, dict), f"csf_score parsed to {type(data)!r}, not a dict"
    assert isinstance(data.get("scores"), list), "csf_score response missing 'scores' list"


def _check_zt(data) -> None:
    assert isinstance(data, dict), f"zt_score parsed to {type(data)!r}, not a dict"
    assert isinstance(
        data.get("capabilities"), list
    ), "zt_score response missing 'capabilities' list"


def _check_mitre(data) -> None:
    assert isinstance(data, dict), f"mitre_map parsed to {type(data)!r}, not a dict"
    assert isinstance(data.get("techniques"), list), "mitre_map response missing 'techniques' list"


def _check_risk(data) -> None:
    assert isinstance(data, dict), f"risk_synthesize parsed to {type(data)!r}, not a dict"
    assert isinstance(data.get("entries"), list), "risk_synthesize response missing 'entries' list"


def _check_tech_debt(data) -> None:
    assert isinstance(data, list), f"tech_debt_extract parsed to {type(data)!r}, not a list"
    assert all(
        isinstance(item, ExtractedCapability) for item in data
    ), "tech_debt_extract did not parse into ExtractedCapability rows"


# (job_name, payload builder, response-parse check) for all five AI purposes.
_CASES = [
    ("csf_score", build_csf_pii_inputs, _check_csf),
    ("zt_score", _build_zt, _check_zt),
    ("mitre_map", _build_mitre, _check_mitre),
    ("risk_synthesize", _build_risk, _check_risk),
    ("tech_debt_extract", _build_tech_debt, _check_tech_debt),
]


@pytest.mark.parametrize("job_name,builder,check", _CASES, ids=[c[0] for c in _CASES])
def test_live_purpose_contract(db_factory, job_name, builder, check) -> None:
    """One real run per AI purpose: redaction stripped the planted PII, the
    audit row is complete, no raw PII survived, and the response parses into the
    purpose's documented container."""
    inputs, client_org_name, name_hints = builder()
    client = LLMClient.from_settings(get_settings())

    with db_factory() as db:
        admin = _new_admin(db)
        result = run_job(
            db,
            client,
            job_name,
            inputs=inputs,
            requested_by=admin.id,
            client_org_name=client_org_name,
            name_hints=name_hints,
        )
        db.commit()
        row = result.llm_call

        # A real, live, completed call — not a fixture, not an error.
        assert row.mode == LLMCallMode.LIVE
        assert row.status == LLMCallStatus.COMPLETED
        assert row.error_message is None
        assert row.provider and row.model
        assert row.input_tokens and row.input_tokens > 0
        assert row.output_tokens and row.output_tokens > 0
        assert row.duration_ms is not None and row.duration_ms >= 0

        # Redaction actually ran on the PII we planted (uniform across purposes).
        assert row.redacted_counts == EXPECTED_REDACTED_COUNTS

        # The response is real and non-empty, and carries none of the raw PII.
        rendered = str(result.data)
        assert rendered.strip()
        for pii in PII_STRINGS:
            assert pii not in rendered

        # Per-adapter parse: the response deserialized into the shape the route
        # layer reads. This is the check T7 exists to run against real output.
        check(result.data)

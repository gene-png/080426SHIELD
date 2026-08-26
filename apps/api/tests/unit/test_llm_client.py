"""LLMClient invariants: redaction-before-egress + audit-row-on-every-call."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.config import get_settings
from app.models.llm_call import LLMCall, LLMCallMode, LLMCallStatus
from app.models.user import User, UserRole


@pytest.fixture()
def db_factory(tmp_path) -> Iterator[sessionmaker]:
    db_path = tmp_path / "shield-llm.db"
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
    u = User(
        email="admin@example.com",
        password_hash="x" * 64,
        role=UserRole.ADMIN,
        display_name="Admin",
    )
    db.add(u)
    db.flush()
    return u


@pytest.mark.unit
def test_invoke_writes_llm_call_row_with_completed_status(db_factory) -> None:
    provider = FixtureProvider()
    captured: dict = {}

    def fake(payload: dict) -> LLMResponse:
        captured.update(payload)
        return LLMResponse("ok", input_tokens=12, output_tokens=34)

    provider.register("extract.capabilities", fake)
    client = LLMClient(provider, settings=get_settings())

    with db_factory() as db:
        admin = _new_admin(db)
        response, row = client.invoke(
            db,
            purpose="extract.capabilities",
            prompt="Extract the capability list.",
            payload={
                "filename": "inventory.csv",
                "contact": "alice@example.gov",
                "ssn": "123-45-6789",
            },
            requested_by=admin.id,
        )
        db.commit()

        assert response.content == "ok"
        assert row.status == LLMCallStatus.COMPLETED
        assert row.input_tokens == 12
        assert row.output_tokens == 34
        assert row.purpose == "extract.capabilities"
        assert row.provider == "fixture"
        assert row.mode == LLMCallMode.FIXTURE
        assert row.requested_by == admin.id
        # Redacted counts captured.
        assert row.redacted_counts is not None
        assert row.redacted_counts["email"] == 1
        assert row.redacted_counts["ssn"] == 1
        # #144: the ledger records the mode the redactor actually ran under.
        assert row.redaction_mode == "strict"

    # Provider received the REDACTED payload, never the raw one.
    assert "alice@example.gov" not in captured.values()
    assert "123-45-6789" not in captured.values()
    assert captured["contact"] == "[EMAIL]"
    assert captured["ssn"] == "[SSN]"


@pytest.mark.unit
def test_invoke_records_failure_with_error_message(db_factory) -> None:
    provider = FixtureProvider()

    def boom(_payload: dict) -> LLMResponse:
        raise RuntimeError("upstream down")

    provider.register("extract.capabilities", boom)
    client = LLMClient(provider)

    with db_factory() as db:
        admin = _new_admin(db)
        with pytest.raises(RuntimeError, match="upstream down"):
            client.invoke(
                db,
                purpose="extract.capabilities",
                prompt="x",
                payload={"a": 1},
                requested_by=admin.id,
            )
        db.commit()

        row = db.execute(select(LLMCall)).scalar_one()
        assert row.status == LLMCallStatus.FAILED
        assert "upstream down" in row.error_message
        # Duration was still recorded so debugging "slow failures" is possible.
        assert row.duration_ms is not None and row.duration_ms >= 0


@pytest.mark.unit
def test_invoke_routes_redacted_payload_in_dict_keys_preserved(db_factory) -> None:
    """Field names like "email" stay readable; only values redact."""
    provider = FixtureProvider()
    seen: dict = {}

    def cap(payload: dict) -> LLMResponse:
        seen.update(payload)
        return LLMResponse("ok")

    provider.register("default", cap)
    client = LLMClient(provider)
    with db_factory() as db:
        admin = _new_admin(db)
        client.invoke(
            db,
            purpose="extract.capabilities",
            prompt="x",
            payload={"poc_email": "a@b.gov", "poc_phone": "555-867-5309"},
            requested_by=admin.id,
        )
    assert "poc_email" in seen and seen["poc_email"] == "[EMAIL]"
    assert "poc_phone" in seen and seen["poc_phone"] == "[PHONE]"


@pytest.mark.unit
def test_fixture_provider_raises_when_purpose_unregistered(db_factory) -> None:
    """Forgetting to register a fixture fails loudly, not silently."""
    provider = FixtureProvider()  # no registrations
    client = LLMClient(provider)
    with db_factory() as db:
        admin = _new_admin(db)
        with pytest.raises(KeyError, match="No fixture registered"):
            client.invoke(
                db,
                purpose="some.unregistered",
                prompt="x",
                payload={},
                requested_by=admin.id,
            )
        db.rollback()


@pytest.mark.unit
def test_correlation_id_threaded_through_llm_call_row(db_factory) -> None:
    from app.logging import correlation_id_var

    provider = FixtureProvider()
    provider.register("p", lambda _p: LLMResponse("ok"))
    client = LLMClient(provider)
    token = correlation_id_var.set("cid-llm-001")
    try:
        with db_factory() as db:
            admin = _new_admin(db)
            client.invoke(
                db,
                purpose="p",
                prompt="x",
                payload={},
                requested_by=admin.id,
            )
            db.commit()
            row = db.execute(select(LLMCall)).scalar_one()
            assert row.correlation_id == "cid-llm-001"
    finally:
        correlation_id_var.reset(token)


@pytest.mark.unit
@pytest.mark.parametrize("requested_mode", ["strict", "standard", "off"])
def test_the_row_records_the_mode_the_call_actually_ran_under(
    db_factory, requested_mode: str
) -> None:
    """#144, end to end through the production writer, for every mode.

    The other tests in `test_llm_call_redaction_mode.py` assert this over SOURCE
    TEXT and over the ORM model -- neither runs a call, so before this test the
    property "the mode is recorded, for every mode" was demonstrated for ZERO
    modes against a real database.

    `off` is the case #144 exists for: the redactor returns the payload
    unchanged and `redacted_counts` stores NULL, byte-identical to a strict run
    that found nothing to remove. The row is only distinguishable if
    `redaction_mode` is populated -- so that pairing is what gets asserted.

    The per-call ARGUMENT is used rather than the setting on purpose: a writer
    that records `self._settings.shield_redaction_mode` instead of the value it
    handed the redactor passes every source-text assertion in this slice
    (verified by mutation, 2026-08-25) and reports a mode the call never ran
    under.

    Parametrised over the whole domain rather than sampled, and that is what
    catches it: under that mutation `[strict]` PASSES, because the setting
    defaults to strict and the wrong variable coincidentally holds the right
    value. Only `[standard]` and `[off]` go red. **A single-mode test would have
    proved nothing.** Same lesson as pinning `get_args(Environment)` rather than
    one environment -- when a value has a domain, cover the domain.
    """
    provider = FixtureProvider()
    provider.register(
        "extract.capabilities", lambda payload: LLMResponse("ok", input_tokens=1, output_tokens=1)
    )
    client = LLMClient(provider, settings=get_settings())

    with db_factory() as db:
        admin = _new_admin(db)
        _, row = client.invoke(
            db,
            purpose="extract.capabilities",
            prompt="Extract the capability list.",
            payload={"contact": "alice@example.gov"},
            requested_by=admin.id,
            redaction_mode=requested_mode,
        )
        db.commit()

        persisted = db.execute(select(LLMCall)).scalar_one()
        assert persisted.redaction_mode == requested_mode, (
            f"the row claims mode {persisted.redaction_mode!r} for a call made "
            f"with {requested_mode!r} -- the ledger is not evidence of what ran"
        )
        assert row.redaction_mode == requested_mode

        if requested_mode == "off":
            # The pairing that #144 exists to break: nothing removed, AND the
            # row says why. Without the second half these bytes are identical
            # to a clean strict run.
            assert persisted.redacted_counts is None

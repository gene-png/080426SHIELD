"""The live-or-fixture stamp every deliverable prints (#646).

Two halves. The state table is pinned case by case, written from the issue
("a deliverable built from fixture output must say so") rather than from the
function. The counting half runs against a migrated database, seeding
`llm_calls` rows the way `LLMClient` writes them.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ai_mode_stamp import (
    UNKNOWN_AI_MODE,
    AiModeStamp,
    ai_mode_for_risk_register,
    ai_mode_for_service,
)
from app.models import Client, User, UserRole
from app.models.llm_call import LLMCall, LLMCallMode, LLMCallStatus
from app.models.service import Service, ServiceKind, ServiceStatus

# ---------------------------------------------------------------------------
# The state table
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("live", "fixture", "looked", "state", "warns"),
    [
        (0, 0, False, "unknown", True),
        (0, 0, True, "none", False),
        (3, 0, True, "live", False),
        (0, 2, True, "fixture", True),
        (3, 2, True, "mixed", True),
        # Counts on an unlooked stamp are ignored: nobody looked.
        (5, 0, False, "unknown", True),
    ],
)
def test_state_and_whether_it_warns(live, fixture, looked, state, warns) -> None:
    stamp = AiModeStamp(live_calls=live, fixture_calls=fixture, looked=looked)
    assert stamp.state == state
    assert stamp.is_warning is warns


@pytest.mark.unit
def test_a_fixture_document_says_so_in_words_a_client_can_read() -> None:
    line = AiModeStamp(live_calls=0, fixture_calls=4).sentence()
    assert line.startswith("OFFLINE TEST DATA:")
    assert "not a live AI model" in line
    assert "placeholders, not analysis" in line


@pytest.mark.unit
def test_a_mixed_document_names_how_many_calls_were_fixtures() -> None:
    line = AiModeStamp(live_calls=3, fixture_calls=2).sentence()
    assert line.startswith("OFFLINE TEST DATA: 2 of the 5 AI calls")


@pytest.mark.unit
def test_a_live_document_does_not_carry_the_warning() -> None:
    line = AiModeStamp(live_calls=3, fixture_calls=0).sentence()
    assert line == "AI suggestions behind this document came from a live AI model."
    assert "OFFLINE" not in line


@pytest.mark.unit
def test_nobody_looked_is_not_the_same_sentence_as_no_ai() -> None:
    none = AiModeStamp(live_calls=0, fixture_calls=0).sentence()
    unknown = UNKNOWN_AI_MODE.sentence()
    assert none != unknown
    assert unknown.startswith("Not recorded whether")
    assert none.startswith("No AI call is recorded")


# ---------------------------------------------------------------------------
# Counting what `llm_calls` holds
# ---------------------------------------------------------------------------


@pytest.fixture()
def db(tmp_path) -> Session:
    url = f"sqlite:///{tmp_path / 'ai-mode.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    with Session(create_engine(url)) as session:
        yield session


def _world(db: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    client = Client(legal_name="Tenant A")
    user = User(
        email="admin@example.com",
        password_hash="x" * 64,
        role=UserRole.ADMIN,
        display_name="Admin",
    )
    db.add_all([client, user])
    db.flush()
    svc = Service(
        kind=ServiceKind.ATTACK_COVERAGE,
        status=ServiceStatus.IN_PROGRESS,
        title="ATT&CK",
        client_id=client.id,
        opened_by=user.id,
    )
    db.add(svc)
    db.flush()
    return client.id, user.id, svc.id


def _call(
    db: Session,
    *,
    user_id: uuid.UUID,
    mode: LLMCallMode,
    status: LLMCallStatus = LLMCallStatus.COMPLETED,
    service_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    purpose: str = "mitre_map",
) -> None:
    db.add(
        LLMCall(
            purpose=purpose,
            prompt_version="v1",
            provider="fixture" if mode == LLMCallMode.FIXTURE else "anthropic",
            model="m",
            mode=mode,
            status=status,
            requested_by=user_id,
            service_id=service_id,
            client_id=client_id,
        )
    )
    db.flush()


@pytest.mark.unit
def test_a_service_counts_its_own_completed_calls_by_mode(db: Session) -> None:
    client_id, user_id, svc_id = _world(db)
    for _ in range(3):
        _call(db, user_id=user_id, mode=LLMCallMode.LIVE, service_id=svc_id)
    _call(db, user_id=user_id, mode=LLMCallMode.FIXTURE, service_id=svc_id)

    stamp = ai_mode_for_service(db, svc_id)
    assert (stamp.live_calls, stamp.fixture_calls, stamp.state) == (3, 1, "mixed")


@pytest.mark.unit
def test_a_failed_call_put_nothing_in_the_document(db: Session) -> None:
    _client_id, user_id, svc_id = _world(db)
    _call(db, user_id=user_id, mode=LLMCallMode.LIVE, service_id=svc_id)
    _call(
        db,
        user_id=user_id,
        mode=LLMCallMode.FIXTURE,
        service_id=svc_id,
        status=LLMCallStatus.FAILED,
    )
    _call(
        db,
        user_id=user_id,
        mode=LLMCallMode.FIXTURE,
        service_id=svc_id,
        status=LLMCallStatus.RUNNING,
    )
    assert ai_mode_for_service(db, svc_id).state == "live"


@pytest.mark.unit
def test_another_services_calls_do_not_count(db: Session) -> None:
    _client_id, user_id, svc_id = _world(db)
    _call(db, user_id=user_id, mode=LLMCallMode.FIXTURE, service_id=uuid.uuid4())
    stamp = ai_mode_for_service(db, svc_id)
    assert stamp.state == "none"
    assert stamp.looked is True


@pytest.mark.unit
def test_the_risk_register_counts_the_clients_risk_calls_only(db: Session) -> None:
    client_id, user_id, svc_id = _world(db)
    _call(
        db,
        user_id=user_id,
        mode=LLMCallMode.FIXTURE,
        client_id=client_id,
        purpose="risk_synthesize",
    )
    _call(
        db, user_id=user_id, mode=LLMCallMode.LIVE, client_id=client_id, purpose="risk_synthesize"
    )
    # Same client, another purpose: a service's own calls are not the register's.
    _call(
        db,
        user_id=user_id,
        mode=LLMCallMode.FIXTURE,
        client_id=client_id,
        service_id=svc_id,
        purpose="mitre_map",
    )
    # Another client's risk call.
    _call(
        db,
        user_id=user_id,
        mode=LLMCallMode.FIXTURE,
        client_id=uuid.uuid4(),
        purpose="risk_synthesize",
    )

    stamp = ai_mode_for_risk_register(db, client_id)
    assert (stamp.live_calls, stamp.fixture_calls) == (1, 1)

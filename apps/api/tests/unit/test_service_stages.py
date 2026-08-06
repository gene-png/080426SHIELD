"""Derived progress stages, and the version trap they have to survive.

`llm_calls` has no version column and `Deliverable.version` is its own counter,
so the naive query — "has this service ever had a completed run?" — lights up
`analyze` on a fresh draft because an earlier draft was analysed. The whole
point of anchoring to the version's `created_at` is to make that impossible.

The stale-evidence tests below are the ones that matter; the table tests just
pin the mapping.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.client import Client
from app.models.deliverable import Deliverable
from app.models.llm_call import LLMCall, LLMCallMode, LLMCallStatus
from app.models.service import Service, ServiceKind
from app.models.user import User, UserRole
from app.services.stages import (
    STAGE_KEYS,
    analysis_ran_for_version,
    deliverable_exists_for_version,
    derive_stages,
)

T0 = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture()
def db(tmp_path):
    """Schema via alembic, not `create_all`.

    `create_all` cannot build this schema on SQLite — `client.service_interests`
    is JSONB, which the SQLite compiler refuses to render. The migrations are
    SQLite-safe by policy, so they are the only correct way to get a test DB.
    """
    url = f"sqlite:///{tmp_path / 'stages.db'}"
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url, future=True)
    session: Session = sessionmaker(bind=engine, future=True)()
    yield session
    session.close()


_user_seq = iter(range(1000))


def _user(db: Session) -> User:
    u = User(
        email=f"a{next(_user_seq)}@example.com",
        password_hash="x",
        display_name="A",
        role=UserRole.ADMIN,
    )
    db.add(u)
    db.flush()
    return u


def _service(db: Session, kind: ServiceKind = ServiceKind.TECH_DEBT) -> Service:
    client = Client(legal_name="Northwind")
    db.add(client)
    db.flush()
    # services.opened_by is NOT NULL — a service always has a consultant.
    svc = Service(kind=kind, client_id=client.id, title="S", opened_by=_user(db).id)
    db.add(svc)
    db.flush()
    return svc


def _run(
    db: Session,
    svc: Service,
    user: User,
    *,
    at: datetime,
    purpose: str = "extract.capabilities",
    status: LLMCallStatus = LLMCallStatus.COMPLETED,
) -> None:
    db.add(
        LLMCall(
            service_id=svc.id,
            purpose=purpose,
            prompt_version="v2",
            provider="fixture",
            model="m",
            mode=LLMCallMode.FIXTURE,
            status=status,
            requested_by=user.id,
            requested_at=at,
        )
    )
    db.flush()


# --------------------------------------------------------------------------- #
# The version trap
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_a_run_from_an_earlier_draft_does_not_analyze_a_newer_one(db) -> None:
    """THE regression this module exists to prevent.

    Draft v1 is created and analysed. The consultant discards it and extracts a
    fresh v2. v2 has had no AI run of its own and must not claim otherwise.
    """
    svc = _service(db)
    user = _user(db)
    v1_created = T0
    _run(db, svc, user, at=v1_created + timedelta(minutes=5))
    v2_created = T0 + timedelta(days=1)

    assert (
        analysis_ran_for_version(
            db, service_id=svc.id, kind=svc.kind, version_created_at=v1_created
        )
        is True
    )
    assert (
        analysis_ran_for_version(
            db, service_id=svc.id, kind=svc.kind, version_created_at=v2_created
        )
        is False
    )


@pytest.mark.unit
def test_a_re_run_on_the_current_version_does_analyze_it(db) -> None:
    """The other half: once v2 is actually analysed, it says so."""
    svc = _service(db)
    user = _user(db)
    v2_created = T0 + timedelta(days=1)
    _run(db, svc, user, at=v2_created - timedelta(hours=1))  # stale, from v1
    _run(db, svc, user, at=v2_created + timedelta(minutes=2))  # this version

    assert (
        analysis_ran_for_version(
            db, service_id=svc.id, kind=svc.kind, version_created_at=v2_created
        )
        is True
    )


@pytest.mark.unit
def test_a_run_exactly_at_version_creation_counts_for_it(db) -> None:
    """Tech Debt mints the list and runs the extraction in one request, so the
    timestamps can be identical. A strict `>` would lose every extraction."""
    svc = _service(db)
    user = _user(db)
    _run(db, svc, user, at=T0)
    assert (
        analysis_ran_for_version(db, service_id=svc.id, kind=svc.kind, version_created_at=T0)
        is True
    )


@pytest.mark.unit
def test_a_failed_run_does_not_count_as_analyzed(db) -> None:
    svc = _service(db)
    user = _user(db)
    _run(db, svc, user, at=T0 + timedelta(minutes=1), status=LLMCallStatus.FAILED)
    assert (
        analysis_ran_for_version(db, service_id=svc.id, kind=svc.kind, version_created_at=T0)
        is False
    )


@pytest.mark.unit
def test_another_services_run_does_not_count(db) -> None:
    """Scoped by service, not just by time."""
    svc = _service(db)
    other = _service(db)
    user = _user(db)
    _run(db, other, user, at=T0 + timedelta(minutes=1))
    assert (
        analysis_ran_for_version(db, service_id=svc.id, kind=svc.kind, version_created_at=T0)
        is False
    )


@pytest.mark.unit
def test_a_different_purpose_does_not_count_as_analysis(db) -> None:
    """Drafting narrative is not analysing. A generate-purpose call must not
    light the analyze stage."""
    svc = _service(db, ServiceKind.ATTACK_COVERAGE)
    user = _user(db)
    _run(db, svc, user, at=T0 + timedelta(minutes=1), purpose="generate.exec_summary")
    assert (
        analysis_ran_for_version(db, service_id=svc.id, kind=svc.kind, version_created_at=T0)
        is False
    )
    _run(db, svc, user, at=T0 + timedelta(minutes=2), purpose="mitre_map")
    assert (
        analysis_ran_for_version(db, service_id=svc.id, kind=svc.kind, version_created_at=T0)
        is True
    )


@pytest.mark.unit
def test_a_deliverable_from_an_earlier_version_does_not_count(db) -> None:
    """Same trap on the generate stage: `Deliverable.version` counts
    deliverables, not assessment versions, so only the timestamp can tell."""
    svc = _service(db)
    db.add(Deliverable(service_id=svc.id, title="v1 report", version=1, created_at=T0))
    db.flush()
    v2_created = T0 + timedelta(days=1)

    assert deliverable_exists_for_version(db, service_id=svc.id, version_created_at=T0) is True
    assert (
        deliverable_exists_for_version(db, service_id=svc.id, version_created_at=v2_created)
        is False
    )


# --------------------------------------------------------------------------- #
# The stage mapping
# --------------------------------------------------------------------------- #


def _states(stages) -> dict[str, str]:
    return {s.key: s.state for s in stages}


@pytest.mark.unit
def test_tech_debt_needs_no_client_submission_to_be_prepared() -> None:
    """Tech Debt and ATT&CK have no self-assessment step, so `prepare` is not
    gated on one — there is no permanently-dead stage in their bar."""
    states = _states(
        derive_stages(
            kind=ServiceKind.TECH_DEBT,
            status="draft",
            client_input_received=False,
            analyzed=False,
            generated=False,
        )
    )
    assert states["prepare"] == "complete"
    assert states["analyze"] == "current"


@pytest.mark.unit
def test_zero_trust_waits_on_the_client_submission() -> None:
    kw = {
        "kind": ServiceKind.ZERO_TRUST_CISA,
        "status": "draft",
        "analyzed": True,
        "generated": False,
    }
    waiting = _states(derive_stages(client_input_received=False, **kw))
    assert waiting["prepare"] == "current"
    # Analysis evidence exists, but the stage before it has not happened — the
    # bar must not show a completed stage sitting after an incomplete one.
    assert waiting["analyze"] == "pending"

    arrived = _states(derive_stages(client_input_received=True, **kw))
    assert arrived["prepare"] == "complete"
    assert arrived["analyze"] == "complete"


@pytest.mark.unit
def test_released_version_shows_every_stage_complete() -> None:
    states = _states(
        derive_stages(
            kind=ServiceKind.NIST_CSF,
            status="released",
            client_input_received=True,
            analyzed=True,
            generated=True,
        )
    )
    assert set(states.values()) == {"complete"}


@pytest.mark.unit
def test_exactly_one_stage_is_current() -> None:
    stages = derive_stages(
        kind=ServiceKind.TECH_DEBT,
        status="approved",
        client_input_received=True,
        analyzed=True,
        generated=False,
    )
    assert [s.state for s in stages].count("current") == 1
    assert _states(stages)["generate"] == "current"


@pytest.mark.unit
def test_stage_order_is_stable() -> None:
    """The UI renders these left to right; reordering silently rewrites the
    process it claims to describe."""
    assert STAGE_KEYS == ("prepare", "analyze", "review", "approve", "generate", "release")
    stages = derive_stages(
        kind=ServiceKind.TECH_DEBT,
        status="draft",
        client_input_received=True,
        analyzed=False,
        generated=False,
    )
    assert tuple(s.key for s in stages) == STAGE_KEYS


@pytest.mark.unit
def test_progress_is_monotonic_no_current_marker_behind_completed_work() -> None:
    """Found in the browser, not in a unit test.

    A seeded Tech Debt list whose extraction predates its current version came
    back as `analyze=current` sitting to the LEFT of review/approve/generate all
    complete. A progress bar with its cursor behind finished stages reads as a
    broken step rather than a passed one. Reaching a stage means the ones before
    it are behind you.
    """
    states = _states(
        derive_stages(
            kind=ServiceKind.TECH_DEBT,
            status="approved",
            client_input_received=True,
            analyzed=False,  # no AI run attributable to THIS version
            generated=True,
        )
    )
    assert states["analyze"] == "complete"
    assert states["review"] == "complete"
    assert states["approve"] == "complete"
    assert states["generate"] == "complete"
    assert states["release"] == "current"
    # And still exactly one cursor.
    assert list(states.values()).count("current") == 1


@pytest.mark.unit
def test_monotonic_fill_does_not_invent_progress_that_never_happened() -> None:
    """The fill only reaches backwards from work that IS done. A draft with
    nothing behind it must not light up."""
    states = _states(
        derive_stages(
            kind=ServiceKind.TECH_DEBT,
            status="draft",
            client_input_received=True,
            analyzed=False,
            generated=False,
        )
    )
    assert states["analyze"] == "current"
    assert states["review"] == "pending"
    assert states["release"] == "pending"

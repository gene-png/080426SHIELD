"""#209: the engagement target a deliverable was RENDERED against is frozen.

Four surfaces resolved the target LIVE on every request while the released
document held the number it was rendered with. Change the intake target after
release and the two disagree -- the PDF says "37 gaps at target S4" and the
dashboard beside it says something else, computed from the same approved
answers. Both internally consistent, and one is a number the client never
contracted for.

## WHAT EACH TEST HERE IS FOR, AND WHICH MUTANT IT KILLS

Every assertion below was verified red-on-revert individually, and the three
that matter most are the ones a plausible WRONG implementation still passes:

  * `test_a_frozen_NULL_choice_does_not_fall_back_to_live` kills
    `if deliv.frozen_target is not None`. That mutant is the natural way to
    write this function, it passes every other test in this file, and it
    silently restores the defect for every client who never set a target --
    which is most of them.
  * `test_the_dashboard_reports_the_FROZEN_stage_after_the_intake_target_moves`
    kills the whole feature. It is the only test here that fails if
    `_frozen_or_live_target` returns `(live, None)` unconditionally.
  * `test_finalize_stamps_a_NULL_choice_with_a_NON_null_source` kills
    `frozen_target_source=... if engagement_target is not None else None`, which
    reads like defensiveness and is what makes the mutant above reachable.

The preamble is the one `test_zt_dashboard.py` uses, duplicated per the local
convention rather than imported across test modules (six dashboard test files
already carry it).
"""

from __future__ import annotations

import os
import uuid as _uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.storage.local import LocalFilesystemStorage


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "shield-frozen-target.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    storage = LocalFilesystemStorage(tmp_path / "storage")

    from app.db.session import get_db
    from app.main import create_app
    from app.routes.artifacts import _storage_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_storage_dep] = lambda: storage

    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    _seed = TestSession()
    _tenant = _Client(legal_name="Test Tenant")
    _seed.add(_tenant)
    _seed.flush()
    _seed.add(_ClientDomain(client_id=_tenant.id, domain="example.com"))
    _seed.commit()
    _cid = str(_tenant.id)
    _seed.close()

    with TestClient(app, headers={"X-Client-Id": _cid}) as c:
        yield c


def _session():
    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    return sessionmaker(bind=eng, future=True)()


def _register(c: TestClient, email: str) -> dict:
    r = c.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple!",
            "display_name": email.split("@")[0],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _set_intake_target(svc_id: str, *, zt_stage: int | None = None, csf_tier: int | None = None):
    """Give the service a source request carrying the client's chosen target.

    Called a SECOND time by several tests to MOVE the target after release --
    which is the whole subject of #209 and the reason this writes through the
    ORM: `ServiceRequest.updated_at` has an `onupdate`, and migration 0051's
    fallback backfill reads it.
    """
    from app.models.service import Service as _Service
    from app.models.service_request import ServiceRequest as _SR

    with _session() as s:
        svc = s.get(_Service, _uuid.UUID(svc_id))
        if svc.source_request_id is None:
            sr = _SR(
                client_id=svc.client_id,
                service_type=svc.kind.value,
                requested_by=svc.opened_by,
                zt_target_stage=zt_stage,
                csf_target_tier=csf_tier,
            )
            s.add(sr)
            s.flush()
            svc.source_request_id = sr.id
        else:
            sr = s.get(_SR, svc.source_request_id)
            if zt_stage is not None or csf_tier is not None:
                sr.zt_target_stage = zt_stage
                sr.csf_target_tier = csf_tier
        s.commit()


def _deliverable_freeze(svc_id: str) -> tuple[int | None, str | None]:
    from app.models.deliverable import Deliverable

    with _session() as s:
        d = s.execute(
            select(Deliverable)
            .where(Deliverable.service_id == _uuid.UUID(svc_id))
            .order_by(Deliverable.version.desc())
            .limit(1)
        ).scalar_one()
        return d.frozen_target, d.frozen_target_source


def _overwrite_freeze(svc_id: str, *, value: int | None, source: str | None) -> None:
    """Put a deliverable into a state the CURRENT product cannot mint.

    Only two states here are unreachable from today's writers, and both are
    named at their call sites: `source=None` is a row that predates migration
    0051, and a declined backfill. Everything else these tests use is produced
    by the finalize routes themselves -- which is the point, because a fixture
    building a state no writer can reach is testing a different system.
    """
    from app.models.deliverable import Deliverable

    with _session() as s:
        d = s.execute(
            select(Deliverable)
            .where(Deliverable.service_id == _uuid.UUID(svc_id))
            .order_by(Deliverable.version.desc())
            .limit(1)
        ).scalar_one()
        d.frozen_target = value
        d.frozen_target_source = source
        s.commit()


# ---------------------------------------------------------------------- ZT


def _zt_service(c: TestClient, bearer: str) -> str:
    svc_id = c.post(
        "/zt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": "zero_trust_cisa", "title": "Atlas - Zero Trust"},
    ).json()["id"]
    return svc_id


def _zt_score_approve(c: TestClient, bearer: str, svc_id: str) -> None:
    h = {"Authorization": f"Bearer {bearer}"}
    assessment = c.post(f"/zt/services/{svc_id}/assessments", headers=h).json()
    for ans in assessment["answers"]:
        c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"maturity_stage": 2})
    c.post(f"/zt/assessments/{assessment['id']}/approve", headers=h)


def _zt_finalize_release(c: TestClient, bearer: str, svc_id: str, *, release: bool = True) -> str:
    h = {"Authorization": f"Bearer {bearer}"}
    deliv_id = c.post(f"/zt/services/{svc_id}/deliverables/finalize", headers=h).json()["id"]
    if release:
        assert c.post(f"/zt/deliverables/{deliv_id}/release", headers=h).status_code == 200
    return deliv_id


def _zt_dashboard(c: TestClient, bearer: str, client_id: str, svc_id: str) -> dict:
    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _released_zt(c: TestClient, *, stage: int | None) -> tuple[str, str, str]:
    """A CLIENT bearer, that client's id, and a released ZT service on `stage`.

    Two registrations and the `X-Client-Id` header, as every other dashboard test
    here does: these endpoints are the CLIENT-facing ones, and reading them as
    the admin would exercise the preview path rather than the one #209 is about.
    """
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    admin_bearer = admin["tokens"]["access_token"]
    client_id = client["user"]["client_id"]
    svc_id = _zt_service(c, admin_bearer)
    _set_intake_target(svc_id, zt_stage=stage)
    _zt_score_approve(c, admin_bearer, svc_id)
    _zt_finalize_release(c, admin_bearer, svc_id)
    c.headers["X-Client-Id"] = client_id
    return client["tokens"]["access_token"], client_id, svc_id


@pytest.mark.unit
def test_the_dashboard_reports_the_FROZEN_stage_after_the_intake_target_moves(app_client) -> None:
    """#209, exactly. The one test that fails on a no-op implementation.

    Released against stage 4, then the intake target moves to 2. The released
    PDF still says 4, so the dashboard must too -- and it must say the figures
    were frozen, which is what lets a client tell the two readings apart.
    """
    bearer, client_id, svc_id = _released_zt(app_client, stage=4)

    before = _zt_dashboard(app_client, bearer, client_id, svc_id)
    assert before["target_stage"] == 4, before
    assert before["target_stage_source"] == "client"
    assert before["target_frozen_at"] is not None, (
        "a deliverable finalized by this product must carry a freeze, or the "
        "disclosure reports live for every row and nothing is actually frozen"
    )

    _set_intake_target(svc_id, zt_stage=2)

    after = _zt_dashboard(app_client, bearer, client_id, svc_id)
    assert after["target_stage"] == 4, (
        "the dashboard followed the intake target after release -- this IS #209: "
        f"the released report was rendered against 4 and the screen says {after['target_stage']}"
    )
    assert after["target_frozen_at"] == before["target_frozen_at"]
    # The gap count is the client-facing consequence, and pinning it is what
    # makes this a test about a NUMBER rather than about a field.
    assert after["total_gap_count"] == before["total_gap_count"], (
        "the gap count moved with the intake target, which is the figure a "
        "client compares against their PDF"
    )


@pytest.mark.unit
def test_a_frozen_NULL_choice_does_not_fall_back_to_live(app_client) -> None:
    """THE MUTANT-KILLING TEST: the branch is on the SOURCE, not the VALUE.

    A client who chose nothing freezes as `(None, "finalize")`. Write
    `if deliv.frozen_target is not None` -- which is the natural way to write
    this, and passes every other test here -- and this row falls through to the
    live read. The defect is then preserved for every client who never set a
    target, under a fix that reads as complete.

    So: freeze "no choice", THEN set an intake target. The dashboard must report
    the engine DEFAULT, because that is what the released report used.
    """
    bearer, client_id, svc_id = _released_zt(app_client, stage=None)

    value, source = _deliverable_freeze(svc_id)
    assert (value, source) == (None, "finalize"), (
        "finalize must record a NULL choice as an EXACT freeze, or the state this "
        f"test is about cannot exist: got {(value, source)!r}"
    )

    before = _zt_dashboard(app_client, bearer, client_id, svc_id)
    assert before["target_stage_source"] == "default", before

    _set_intake_target(svc_id, zt_stage=2)

    after = _zt_dashboard(app_client, bearer, client_id, svc_id)
    assert after["target_stage_source"] == "default", (
        "a frozen NULL choice fell back to the live read -- the branch is keyed "
        "on `frozen_target` rather than `frozen_target_source`"
    )
    assert after["target_stage"] == before["target_stage"]
    assert after["target_frozen_at"] is not None


@pytest.mark.unit
def test_an_unfrozen_deliverable_reads_LIVE_and_discloses_it(app_client) -> None:
    """The legacy row, and the direction the fallback must go.

    A deliverable predating migration 0051 carries no freeze. It must compute
    live -- the behaviour that shipped before #209 -- and SAY SO, because those
    figures can disagree with the document beside them. The null stamp is the
    whole disclosure.
    """
    bearer, client_id, svc_id = _released_zt(app_client, stage=4)
    # Unreachable from today's writers: this is a pre-0051 row, or one 0051's
    # backfill declined.
    _overwrite_freeze(svc_id, value=None, source=None)

    _set_intake_target(svc_id, zt_stage=2)

    after = _zt_dashboard(app_client, bearer, client_id, svc_id)
    assert after["target_frozen_at"] is None, (
        "an unfrozen deliverable reported a freeze stamp, so a client cannot "
        "tell a live figure from a frozen one -- which is the disclosure"
    )
    assert after["target_stage"] == 2, (
        "an unfrozen deliverable did NOT fall back to the live read, so a "
        "pre-0051 row shows a target from nowhere"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stage", "expected_value"),
    [
        (4, 4),
        (2, 2),
        # Out of range on CISA's ladder. The CHOSEN value is frozen verbatim,
        # not the resolved default: the resolver is deterministic, so freezing
        # its input reproduces both the number AND the `client_out_of_range`
        # source, and relabelling the client's broken choice as "no choice" is
        # the one thing a freeze must not do.
        (9, 9),
        (None, None),
    ],
)
def test_finalize_stamps_the_CHOSEN_value_verbatim(app_client, stage, expected_value) -> None:
    bearer, _client_id, svc_id = _released_zt(app_client, stage=stage)
    assert _deliverable_freeze(svc_id) == (expected_value, "finalize")


@pytest.mark.unit
def test_finalize_stamps_a_NULL_choice_with_a_NON_null_source(app_client) -> None:
    """The one that stops the defect being reintroduced defensively.

    `frozen_target_source=X if engagement_target is not None else None` reads
    like care and makes a NULL choice indistinguishable from a pre-0051 row --
    re-arming the mutant `test_a_frozen_NULL_choice_...` exists to kill, from
    the WRITE side where that test cannot see it.
    """
    _bearer, _client_id, svc_id = _released_zt(app_client, stage=None)
    value, source = _deliverable_freeze(svc_id)
    assert value is None
    assert source == "finalize", (
        "a NULL choice was stamped with a NULL source, so it is now "
        "indistinguishable from a deliverable that predates migration 0051"
    )


@pytest.mark.unit
def test_the_out_of_range_source_survives_the_freeze(app_client) -> None:
    """A freeze must not launder a fault into a default.

    `client_out_of_range` is the one target state a consultant can act on by
    re-asking the client. Freezing the RESOLVED value instead of the chosen one
    would report the same NUMBER with the source reading `default` -- the client
    is told they chose nothing when they chose something that was discarded.
    """
    bearer, client_id, svc_id = _released_zt(app_client, stage=9)
    data = _zt_dashboard(app_client, bearer, client_id, svc_id)
    assert data["target_stage_source"] == "client_out_of_range", data
    assert data["target_frozen_at"] is not None


# ---------------------------------------------------------------------- CSF
#
# The twin, in the same commit. `CLAUDE.md`: a defect found in one service
# exists in its twins until you have checked, and a half-fix is worse than none
# because the two surfaces then disagree about one client.


def _released_csf(c: TestClient, *, tier: int | None) -> tuple[str, str, str]:
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    h = {"Authorization": f"Bearer {admin['tokens']['access_token']}"}
    svc_id = c.post(
        "/csf/services", headers=h, json={"kind": "nist_csf", "title": "Atlas - CSF"}
    ).json()["id"]
    _set_intake_target(svc_id, csf_tier=tier)
    assessment = c.post(f"/csf/services/{svc_id}/assessments", headers=h).json()
    for ans in assessment["answers"]:
        c.patch(f"/csf/answers/{ans['id']}", headers=h, json={"maturity_tier": 2})
    c.post(f"/csf/assessments/{assessment['id']}/approve", headers=h)
    deliv_id = c.post(f"/csf/services/{svc_id}/deliverables/finalize", headers=h).json()["id"]
    assert c.post(f"/csf/deliverables/{deliv_id}/release", headers=h).status_code == 200
    c.headers["X-Client-Id"] = client["user"]["client_id"]
    return client["tokens"]["access_token"], client["user"]["client_id"], svc_id


def _csf_dashboard(c: TestClient, bearer: str, client_id: str, svc_id: str) -> dict:
    r = c.get(
        f"/clients/{client_id}/csf/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.unit
def test_the_CSF_dashboard_reports_the_FROZEN_tier_after_the_intake_target_moves(
    app_client,
) -> None:
    bearer, client_id, svc_id = _released_csf(app_client, tier=4)

    before = _csf_dashboard(app_client, bearer, client_id, svc_id)
    assert before["target_tier"] == 4, before
    assert before["target_frozen_at"] is not None

    _set_intake_target(svc_id, csf_tier=2)

    after = _csf_dashboard(app_client, bearer, client_id, svc_id)
    assert after["target_tier"] == 4, (
        "the CSF dashboard followed the intake target after release -- the ZT "
        "twin's defect, one service over"
    )
    assert after["total_gap_count"] == before["total_gap_count"]


@pytest.mark.unit
def test_a_frozen_NULL_choice_does_not_fall_back_to_live_on_CSF(app_client) -> None:
    """The source-vs-value branch, on the twin. Both or neither."""
    bearer, client_id, svc_id = _released_csf(app_client, tier=None)
    assert _deliverable_freeze(svc_id) == (None, "finalize")

    before = _csf_dashboard(app_client, bearer, client_id, svc_id)
    assert before["target_tier_source"] == "default", before

    _set_intake_target(svc_id, csf_tier=2)

    after = _csf_dashboard(app_client, bearer, client_id, svc_id)
    assert after["target_tier_source"] == "default"
    assert after["target_tier"] == before["target_tier"]


# ------------------------------------------------- the cross-service card
#
# The value summary is a DIFFERENT code path over the same fact, and it is the
# surface that sits on the client's home page.


@pytest.mark.unit
def test_the_value_summary_gap_total_uses_the_frozen_target(app_client) -> None:
    bearer, client_id, svc_id = _released_zt(app_client, stage=4)
    h = {"Authorization": f"Bearer {bearer}"}

    before = app_client.get(f"/clients/{client_id}/value-summary", headers=h).json()
    assert before["zt_gap_count"] is not None
    assert before["zt_targets_computed_live"] == 0, before

    _set_intake_target(svc_id, zt_stage=2)

    after = app_client.get(f"/clients/{client_id}/value-summary", headers=h).json()
    assert after["zt_gap_count"] == before["zt_gap_count"], (
        "the home-page card followed the intake target while the per-service "
        "dashboard froze it -- two surfaces, one client, opposite numbers"
    )
    assert after["zt_targets_computed_live"] == 0


@pytest.mark.unit
def test_an_unfrozen_summand_is_COUNTED_rather_than_hidden(app_client) -> None:
    """The disclosure, not just the correctness.

    A live-read summand is not wrong -- it is unverifiable against the document,
    and a count is what makes a mixed set self-describing. `0` here over a live
    read would be the reassuring direction over a fact nobody measured.
    """
    bearer, client_id, svc_id = _released_zt(app_client, stage=4)
    _overwrite_freeze(svc_id, value=None, source=None)

    data = app_client.get(
        f"/clients/{client_id}/value-summary",
        headers={"Authorization": f"Bearer {bearer}"},
    ).json()
    assert data["zt_targets_computed_live"] == 1, (
        "an unfrozen summand was counted as frozen, so the card asserts "
        "agreement with a document it never checked"
    )
    assert data["zt_services"] == 1
    # The two #207 tallies describe a different fault and must NOT absorb this
    # one: the client chose stage 4 and it was usable.
    assert data["zt_targets_defaulted"] == 0
    assert data["zt_targets_unusable"] == 0

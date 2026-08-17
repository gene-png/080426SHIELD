"""Contract tests for the deliverable release-to-client flow (Sprint 5 T1, D-025).

Release is a NEW admin-only action: until a consultant explicitly releases a
finalized deliverable, the client sees nothing (Master Spec §12 release rule).
These tests lock the release route, the client read route, and the artifact
download allow/deny matrix.
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
    db_path = tmp_path / "shield-release.db"
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

    c = TestClient(app, headers={"X-Client-Id": _cid})
    c._tenant_id = _cid  # type: ignore[attr-defined]
    with c:
        yield c


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


def _finalized_csf_deliverable(c: TestClient, bearer: str) -> dict:
    """Open CSF service, score tier 3, approve, finalize. Returns the deliverable."""
    sr = c.post(
        "/csf/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": "nist_csf", "title": "Atlas - CSF"},
    )
    svc_id = sr.json()["id"]
    a = c.post(
        f"/csf/services/{svc_id}/assessments",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assess = a.json()
    for ans in assess["answers"]:
        c.patch(
            f"/csf/answers/{ans['id']}",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"maturity_tier": 3},
        )
    c.post(
        f"/csf/assessments/{assess['id']}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    fin = c.post(
        f"/csf/services/{svc_id}/deliverables/finalize",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert fin.status_code == 201, fin.text
    return fin.json()


# --- Release route -----------------------------------------------------------


@pytest.mark.unit
def test_release_requires_finalized(app_client) -> None:
    """Releasing a deliverable that was never finalized -> typed 409."""
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]

    # Fabricate an unfinalized deliverable directly so the route sees a row
    # without finalized_at.
    from app.db.session import get_db
    from app.models.deliverable import Deliverable
    from app.models.service import Service, ServiceKind

    gen = c.app.dependency_overrides[get_db]()
    db = next(gen)
    svc = Service(
        kind=ServiceKind.NIST_CSF,
        title="raw",
        client_id=_uuid.UUID(c._tenant_id),
        opened_by=_uuid.UUID(admin["user"]["id"]),
    )
    db.add(svc)
    db.flush()
    deliv = Deliverable(service_id=svc.id, title="unfinalized", version=1)
    db.add(deliv)
    db.commit()
    deliv_id = str(deliv.id)
    db.close()

    r = c.post(
        f"/csf/deliverables/{deliv_id}/release",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "not_finalized"


@pytest.mark.unit
def test_release_sets_fields_and_audits(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    deliv = _finalized_csf_deliverable(c, bearer)
    assert deliv["released_at"] is None

    r = c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["released_at"] is not None
    assert body["released_by"] == admin["user"]["id"]

    # An audit row *.deliverable.released was written.
    from app.db.session import get_db
    from app.models.audit_entry import AuditEntry

    gen = c.app.dependency_overrides[get_db]()
    db = next(gen)
    rows = (
        db.execute(select(AuditEntry).where(AuditEntry.action == "csf.deliverable.released"))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert str(rows[0].target_id) == deliv["id"]
    db.close()


@pytest.mark.unit
def test_release_is_idempotent(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    deliv = _finalized_csf_deliverable(c, bearer)

    r1 = c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r1.status_code == 200, r1.text
    first_release = r1.json()["released_at"]

    r2 = c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r2.status_code == 200, r2.text
    # No-op: same released_at, no second audit row.
    assert r2.json()["released_at"] == first_release

    from app.db.session import get_db
    from app.models.audit_entry import AuditEntry

    gen = c.app.dependency_overrides[get_db]()
    db = next(gen)
    rows = (
        db.execute(select(AuditEntry).where(AuditEntry.action == "csf.deliverable.released"))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    db.close()


@pytest.mark.unit
def test_release_requires_admin(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    deliv = _finalized_csf_deliverable(c, bearer_admin)
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    r = c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 403, r.text


@pytest.mark.unit
def test_release_wrong_service_kind_404(app_client) -> None:
    """A CSF deliverable id cannot be released through the zt route."""
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    deliv = _finalized_csf_deliverable(c, bearer)
    r = c.post(
        f"/zt/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 404, r.text


# --- Client list route -------------------------------------------------------


@pytest.mark.unit
def test_client_list_only_released_own_tenant(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    cid = client["user"]["client_id"]

    deliv = _finalized_csf_deliverable(c, bearer_admin)

    # Before release: the client sees nothing.
    r = c.get(
        f"/clients/{cid}/deliverables",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []

    # Release, then the client sees exactly one row with the expected shape.
    c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    )
    r = c.get(
        f"/clients/{cid}/deliverables",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["id"] == deliv["id"]
    assert row["released_at"] is not None
    assert row["version"] == deliv["version"]
    assert row["pdf_filename"].endswith(".pdf")
    assert row["service_kind"] == "nist_csf"


@pytest.mark.unit
def test_client_list_cross_tenant_404(app_client) -> None:
    """A client asking for another tenant's list gets 404 (never 403)."""
    c = app_client
    _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    r = c.get(
        f"/clients/{_uuid.uuid4()}/deliverables",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 404, r.text


# --- Artifact download allow/deny matrix -------------------------------------


@pytest.mark.unit
def test_client_can_download_released_deliverable_artifacts(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]
    deliv = _finalized_csf_deliverable(c, bearer_admin)

    # Unreleased: client denied on every format.
    for key in ("pdf_artifact_id", "xlsx_artifact_id", "docx_artifact_id"):
        d = c.get(
            f"/artifacts/{deliv[key]}/download",
            headers={"Authorization": f"Bearer {bearer_client}"},
        )
        assert d.status_code == 404, f"{key}: {d.status_code}"

    # Release, then the client can download every format.
    c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    )
    for key in ("pdf_artifact_id", "xlsx_artifact_id", "docx_artifact_id"):
        d = c.get(
            f"/artifacts/{deliv[key]}/download",
            headers={"Authorization": f"Bearer {bearer_client}"},
        )
        assert d.status_code == 200, f"{key}: {d.status_code} {d.text}"


@pytest.mark.unit
def test_client_cannot_download_other_tenants_released_artifact(app_client) -> None:
    """Cross-tenant deny: a client of tenant B cannot download tenant A's
    RELEASED deliverable artifact — the tenant boundary 404s (never 403), even
    though the deliverable is released."""
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    deliv = _finalized_csf_deliverable(c, bearer_admin)
    c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    )

    # Seed a SECOND tenant (own domain) and register a client user into it.
    from app.db.session import get_db
    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    gen = c.app.dependency_overrides[get_db]()
    db = next(gen)
    tenant_b = _Client(legal_name="Beta Tenant")
    db.add(tenant_b)
    db.flush()
    db.add(_ClientDomain(client_id=tenant_b.id, domain="beta.example"))
    db.commit()
    tenant_b_id = str(tenant_b.id)
    db.close()

    client_b = _register(c, "client@beta.example")
    assert client_b["user"]["client_id"] == tenant_b_id
    bearer_b = client_b["tokens"]["access_token"]

    d = c.get(
        f"/artifacts/{deliv['pdf_artifact_id']}/download",
        headers={"Authorization": f"Bearer {bearer_b}", "X-Client-Id": tenant_b_id},
    )
    assert d.status_code == 404, d.text


@pytest.mark.unit
def test_client_cannot_download_non_deliverable_artifact(app_client) -> None:
    """A non-deliverable artifact the client didn't upload stays 404 for them."""
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    client = _register(c, "client@example.com")
    bearer_client = client["tokens"]["access_token"]

    up = c.post(
        "/artifacts",
        headers={"Authorization": f"Bearer {bearer_admin}"},
        files={"file": ("notes.txt", b"internal admin notes", "text/plain")},
    )
    assert up.status_code == 201, up.text
    art_id = up.json()["id"]

    d = c.get(
        f"/artifacts/{art_id}/download",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert d.status_code == 404, d.text


# --------------------------------------------------------------------------
# W4 — releasing a deliverable flips its PARENT to RELEASED.
#
# Until now no API route assigned RELEASED anywhere; the only writer in the repo
# was seed_demo.py. So a service released through the product kept a parent that
# still read APPROVED, and `services/stages.py` — which derives `released` from
# the PARENT status, not from `deliverables.released_at` — showed `release` as
# the current incomplete stage on a service whose report was already with the
# client. Option A of the plan's §8, superseding D-035 §1.
# --------------------------------------------------------------------------


def _csf_parent_status(c: TestClient, bearer: str, svc_id: str) -> str:
    r = c.get(
        f"/csf/services/{svc_id}/assessments/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    return r.json()["status"]


@pytest.mark.unit
def test_release_flips_the_parent_assessment_to_released(app_client) -> None:
    """The headline. Before W4 the parent stayed APPROVED forever."""
    c = app_client
    bearer = _register(c, "w4-admin@example.com")["tokens"]["access_token"]
    deliv = _finalized_csf_deliverable(c, bearer)
    svc_id = deliv["service_id"]

    assert _csf_parent_status(c, bearer, svc_id) == "approved"

    r = c.post(
        f"/csf/deliverables/{deliv['id']}/release",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    assert _csf_parent_status(c, bearer, svc_id) == "released"


@pytest.mark.unit
def test_release_flips_the_version_it_was_built_from_not_the_latest(app_client) -> None:
    """The reason migration 0041 records the link instead of inferring it.

    `deliverables.version` and the assessment version are independent counters,
    so "latest APPROVED" is not the same row as "the one this report was built
    from". After approve v1 -> finalize -> cut v2 -> approve v2 -> release, the
    latest-APPROVED rule flips v2, which the released PDF was never built from.
    """
    c = app_client
    bearer = _register(c, "w4-vers@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    deliv = _finalized_csf_deliverable(c, bearer)
    svc_id = deliv["service_id"]

    # Cut a second assessment version and approve it too.
    a2 = c.post(f"/csf/services/{svc_id}/assessments", headers=h)
    assert a2.status_code == 201, a2.text
    v2 = a2.json()
    assert v2["version"] > 1
    ap = c.post(f"/csf/assessments/{v2['id']}/approve", headers=h)
    assert ap.status_code == 200, ap.text

    r = c.post(f"/csf/deliverables/{deliv['id']}/release", headers=h)
    assert r.status_code == 200, r.text

    # v2 is the latest APPROVED and must be untouched; v1 is what got released.
    from app.models.csf_assessment import CsfAssessment

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as check:
        rows = {
            row.version: row.status.value
            for row in check.execute(
                select(CsfAssessment).where(CsfAssessment.service_id == _uuid.UUID(svc_id))
            )
            .scalars()
            .all()
        }
    assert rows[1] == "released", rows
    assert rows[v2["version"]] == "approved", rows


@pytest.mark.unit
def test_release_leaves_a_pre_0041_parent_alone_and_says_so(app_client, capsys) -> None:
    """C0: a deliverable finalized before 0041 has `parent_version` NULL.

    Release must still succeed — it is the source of truth — and must NOT guess a
    parent, because guessing is the thing the column exists to stop. It says so
    in the log instead of silently doing nothing.
    """
    c = app_client
    bearer = _register(c, "w4-legacy@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    deliv = _finalized_csf_deliverable(c, bearer)
    svc_id = deliv["service_id"]

    # Simulate a row written before the migration.
    from app.models.deliverable import Deliverable as _D

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as fix:
        row = fix.get(_D, _uuid.UUID(deliv["id"]))
        row.parent_version = None
        fix.commit()

    capsys.readouterr()
    r = c.post(f"/csf/deliverables/{deliv['id']}/release", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["released_at"] is not None

    out = capsys.readouterr().out
    assert "deliverable.release_parent_unknown" in out, out
    # The parent is left as it was, not guessed at.
    assert _csf_parent_status(c, bearer, svc_id) == "approved"


@pytest.mark.unit
def test_release_does_not_flip_a_draft_parent(app_client, capsys) -> None:
    """Only an APPROVED parent may become RELEASED.

    If the recorded version somehow points at a DRAFT, flipping it would skip
    APPROVED entirely and lock work a consultant is mid-way through. Refuse and
    log, rather than write a transition no route would ever make.
    """
    c = app_client
    bearer = _register(c, "w4-draft@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    deliv = _finalized_csf_deliverable(c, bearer)
    svc_id = deliv["service_id"]

    from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as fix:
        row = (
            fix.execute(select(CsfAssessment).where(CsfAssessment.service_id == _uuid.UUID(svc_id)))
            .scalars()
            .first()
        )
        row.status = CsfAssessmentStatus.DRAFT
        fix.commit()

    capsys.readouterr()
    r = c.post(f"/csf/deliverables/{deliv['id']}/release", headers=h)
    assert r.status_code == 200, r.text

    out = capsys.readouterr().out
    assert "deliverable.release_parent_not_approved" in out, out
    assert _csf_parent_status(c, bearer, svc_id) == "draft"


@pytest.mark.unit
def test_stage_bar_shows_release_complete_after_an_api_release(app_client) -> None:
    """The user-visible defect W4 fixes.

    `stages.py` reads the PARENT status, so before W4 an API-released service
    reported `release` as its current incomplete stage while the client already
    had the report. A test constructing status="released" by hand passed the
    whole time — it was asserting a state no route could reach.
    """
    c = app_client
    bearer = _register(c, "w4-stages@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    deliv = _finalized_csf_deliverable(c, bearer)
    svc_id = deliv["service_id"]

    before = c.get(f"/services/{svc_id}/stages", headers=h)
    assert before.status_code == 200, before.text
    was = {s["key"]: s["state"] for s in before.json()["stages"]}
    # Finalized but unreleased: `release` is the stage still to do.
    assert was["release"] == "current", before.json()

    c.post(f"/csf/deliverables/{deliv['id']}/release", headers=h)

    after = c.get(f"/services/{svc_id}/stages", headers=h)
    assert after.status_code == 200, after.text
    now = {s["key"]: s["state"] for s in after.json()["stages"]}
    assert now["release"] == "complete", after.json()
    # Nothing is left pointing at unfinished work once the client has the report.
    assert "current" not in now.values(), after.json()


@pytest.mark.unit
def test_every_service_kind_has_a_parent_to_release() -> None:
    """A new service kind must not silently release nothing.

    `_PARENTS` is the map W4 introduced; a kind missing from it raises rather
    than skipping the flip, but the raise only fires at release time on a real
    tenant. This turns that into a collection error instead.
    """
    from app.deliverable_release import _PARENTS
    from app.models.service import ServiceKind

    missing = [k for k in ServiceKind if k not in _PARENTS]
    assert missing == [], f"service kinds with no parent record mapped: {missing}"

    # Presence is not enough — a kind mapped to the WRONG table would release
    # some other service's parent. Pin the table each kind resolves to.
    expected = {
        ServiceKind.TECH_DEBT: "capability_lists",
        ServiceKind.NIST_CSF: "csf_assessments",
        ServiceKind.ZERO_TRUST_CISA: "zt_assessments",
        ServiceKind.ZERO_TRUST_DOD: "zt_assessments",
        ServiceKind.ATTACK_COVERAGE: "attack_assessments",
    }
    actual = {k: v.model.__tablename__ for k, v in _PARENTS.items()}
    assert actual == expected
    # Each status enum must carry the two members `_release_parent` reads.
    for kind, parent in _PARENTS.items():
        assert parent.status_enum.APPROVED, kind
        assert parent.status_enum.RELEASED, kind


@pytest.mark.unit
def test_re_releasing_repairs_a_parent_that_never_got_flipped(app_client, capsys) -> None:
    """The repair path for anything released before W4.

    Release is idempotent, so without this a parent stuck on APPROVED could only
    be fixed with direct SQL: re-releasing returned 200 and changed nothing,
    forever, while the progress bar told the consultant a delivered report still
    needed releasing.
    """
    c = app_client
    bearer = _register(c, "w4-repair@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    deliv = _finalized_csf_deliverable(c, bearer)
    svc_id = deliv["service_id"]

    # Release with the link unknown — the pre-0041 shape. Parent stays APPROVED.
    from app.models.deliverable import Deliverable as _D

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as fix:
        fix.get(_D, _uuid.UUID(deliv["id"])).parent_version = None
        fix.commit()

    c.post(f"/csf/deliverables/{deliv['id']}/release", headers=h)
    assert _csf_parent_status(c, bearer, svc_id) == "approved"

    # An operator backfills the link, then re-releases to repair.
    with sessionmaker(bind=engine, future=True)() as fix:
        fix.get(_D, _uuid.UUID(deliv["id"])).parent_version = 1
        fix.commit()

    capsys.readouterr()
    again = c.post(f"/csf/deliverables/{deliv['id']}/release", headers=h)
    assert again.status_code == 200, again.text
    assert _csf_parent_status(c, bearer, svc_id) == "released"
    out = capsys.readouterr().out
    # Still reported as the idempotent no-op it is — the repair is not a lie
    # that the deliverable was released a second time.
    assert "already released" in out, out


@pytest.mark.unit
def test_releasing_a_second_version_does_not_warn_about_the_parent(app_client, capsys) -> None:
    """Finalize accepts a RELEASED parent, so release-then-refinalize-then-release
    is a normal flow that lands on an already-RELEASED parent. It must not log the
    warning that exists to surface a genuinely stuck parent, or that warning is
    noise on a healthy run and stops being read.
    """
    c = app_client
    bearer = _register(c, "w4-v2@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    deliv = _finalized_csf_deliverable(c, bearer)
    svc_id = deliv["service_id"]
    c.post(f"/csf/deliverables/{deliv['id']}/release", headers=h)

    v2 = c.post(f"/csf/services/{svc_id}/deliverables/finalize", headers=h)
    assert v2.status_code == 201, v2.text

    capsys.readouterr()
    r = c.post(f"/csf/deliverables/{v2.json()['id']}/release", headers=h)
    assert r.status_code == 200, r.text
    out = capsys.readouterr().out
    assert "release_parent_already_released" in out, out
    assert "release_parent_not_approved" not in out, out


@pytest.mark.unit
def test_approve_after_release_is_a_409_not_a_silent_success(app_client) -> None:
    """This 409 was dead code: nothing ever assigned RELEASED, so approve-after-
    release returned an idempotent 200. W4 makes the guard live.
    """
    c = app_client
    bearer = _register(c, "w4-approve@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    deliv = _finalized_csf_deliverable(c, bearer)
    svc_id = deliv["service_id"]

    a = c.get(f"/csf/services/{svc_id}/assessments/latest", headers=h)
    assessment_id = a.json()["id"]

    c.post(f"/csf/deliverables/{deliv['id']}/release", headers=h)

    r = c.post(f"/csf/assessments/{assessment_id}/approve", headers=h)
    assert r.status_code == 409, r.text

"""HTTP-level tests for the CSF 2.0 service routes."""

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

from app.csf.catalog import SUBCATEGORIES


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "shield-csf.db"
    url = f"sqlite:///{db_path}"
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

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    # Multi-tenant (post-0013): admin/reviewer callers must name an active
    # tenant via X-Client-Id. Seed one tenant and bake the header into the
    # test client so single-tenant-style tests resolve to it; client-role
    # callers are pinned to their own client and ignore this header.
    from app.models.client import Client as _Client

    _seed = TestSession()
    _tenant = _Client(legal_name="Test Tenant")
    _seed.add(_tenant)
    _seed.flush()
    from app.models.client_domain import ClientDomain as _ClientDomain

    _seed.add(_ClientDomain(client_id=_tenant.id, domain="example.com"))
    _seed.commit()
    _cid = str(_tenant.id)
    _seed.close()

    with TestClient(app, headers={"X-Client-Id": _cid}) as c:
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


def _open_service(c: TestClient, bearer: str, title: str = "NIST CSF") -> str:
    r = c.post(
        "/csf/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": "nist_csf", "title": title},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _new_assessment(c: TestClient, bearer: str, svc_id: str) -> dict:
    r = c.post(
        f"/csf/services/{svc_id}/assessments",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.unit
def test_catalog_endpoint_returns_106_subcategories(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    r = c.get("/csf/catalog", headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code == 200
    body = r.json()
    assert body["total_subcategories"] == 106
    assert len(body["functions"]) == 6
    assert len(body["tiers"]) == 4
    # Spot-check the structure of the first function.
    gv = body["functions"][0]
    assert gv["code"] == "GV"
    assert gv["name"] == "GOVERN"
    sub_count = sum(len(cat["subcategories"]) for cat in gv["categories"])
    assert sub_count == 31


@pytest.mark.unit
def test_admin_can_open_csf_service(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id = _open_service(c, bearer)
    assert svc_id


@pytest.mark.unit
def test_client_cannot_open_csf_service(app_client) -> None:
    c = app_client
    _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    c.headers["X-Client-Id"] = client["user"]["client_id"]
    bearer = client["tokens"]["access_token"]
    r = c.post(
        "/csf/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": "nist_csf", "title": "x"},
    )
    assert r.status_code == 403


@pytest.mark.unit
def test_create_assessment_seeds_106_empty_answers(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id = _open_service(c, bearer)
    body = _new_assessment(c, bearer, svc_id)
    assert body["version"] == 1
    assert body["status"] == "draft"
    assert len(body["answers"]) == 106
    # All start unscored.
    assert all(a["maturity_tier"] is None for a in body["answers"])


@pytest.mark.unit
def test_create_assessment_increments_version_after_prior_closed(app_client) -> None:
    # T7 draft-exists guard: a second POST while a draft is open reuses it
    # (see test_csf_draft_guard.py). A new version is only cut once the prior
    # draft is closed — approve v1, then POST mints v2.
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id = _open_service(c, bearer)
    v1 = _new_assessment(c, bearer, svc_id)
    approved = c.post(
        f"/csf/assessments/{v1['id']}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert approved.status_code == 200, approved.text
    v2 = _new_assessment(c, bearer, svc_id)
    assert v1["version"] == 1
    assert v2["version"] == 2
    assert v1["id"] != v2["id"]


@pytest.mark.unit
def test_patch_answer_records_score_and_actor(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id = _open_service(c, bearer)
    a = _new_assessment(c, bearer, svc_id)
    # Pick the first answer.
    answer = a["answers"][0]
    r = c.patch(
        f"/csf/answers/{answer['id']}",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"maturity_tier": 3, "notes": "Verified via SSP."},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["maturity_tier"] == 3
    assert body["notes"] == "Verified via SSP."
    assert body["answered_by"] is not None
    assert body["answered_at"] is not None


@pytest.mark.unit
def test_patch_answer_rejects_bad_tier(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id = _open_service(c, bearer)
    a = _new_assessment(c, bearer, svc_id)
    r = c.patch(
        f"/csf/answers/{a['answers'][0]['id']}",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"maturity_tier": 99},
    )
    assert r.status_code == 422


@pytest.mark.unit
def test_patch_answer_rejects_empty_body(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id = _open_service(c, bearer)
    a = _new_assessment(c, bearer, svc_id)
    r = c.patch(
        f"/csf/answers/{a['answers'][0]['id']}",
        headers={"Authorization": f"Bearer {bearer}"},
        json={},
    )
    assert r.status_code == 400


@pytest.mark.unit
def test_patch_answer_404_for_unknown(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    r = c.patch(
        f"/csf/answers/{_uuid.uuid4()}",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"maturity_tier": 2},
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_patch_answer_rejects_client_role(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    client = _register(c, "client@example.com")
    c.headers["X-Client-Id"] = client["user"]["client_id"]
    bearer_client = client["tokens"]["access_token"]
    svc_id = _open_service(c, bearer_admin)
    a = _new_assessment(c, bearer_admin, svc_id)
    r = c.patch(
        f"/csf/answers/{a['answers'][0]['id']}",
        headers={"Authorization": f"Bearer {bearer_client}"},
        json={"maturity_tier": 2},
    )
    assert r.status_code == 403


@pytest.mark.unit
def test_approve_assessment_locks_edits(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id = _open_service(c, bearer)
    a = _new_assessment(c, bearer, svc_id)
    r = c.post(
        f"/csf/assessments/{a['id']}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    # Second approve is idempotent.
    r2 = c.post(
        f"/csf/assessments/{a['id']}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r2.status_code == 200
    # And edits now fail with 409.
    r3 = c.patch(
        f"/csf/answers/{a['answers'][0]['id']}",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"maturity_tier": 4},
    )
    assert r3.status_code == 409


@pytest.mark.unit
def test_score_endpoint_aggregates_answers(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id = _open_service(c, bearer)
    a = _new_assessment(c, bearer, svc_id)
    # Answer all 106 with tier 3.
    for ans in a["answers"]:
        c.patch(
            f"/csf/answers/{ans['id']}",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"maturity_tier": 3},
        )
    r = c.get(
        f"/csf/services/{svc_id}/score",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_subcategories"] == 106
    assert body["answered_subcategories"] == 106
    assert body["coverage_pct"] == 100.0
    assert body["average_tier"] == 3.0
    assert body["overall_maturity_label"] == "Repeatable"
    assert len(body["by_function"]) == 6


@pytest.mark.unit
def test_score_endpoint_404_when_no_assessment(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id = _open_service(c, bearer)
    r = c.get(
        f"/csf/services/{svc_id}/score",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_latest_assessment_admin_only_until_released(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    client = _register(c, "client@example.com")
    c.headers["X-Client-Id"] = client["user"]["client_id"]
    bearer_client = client["tokens"]["access_token"]
    svc_id = _open_service(c, bearer_admin)
    _new_assessment(c, bearer_admin, svc_id)
    # Admin can read.
    r = c.get(
        f"/csf/services/{svc_id}/assessments/latest",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    )
    assert r.status_code == 200
    # Client cannot until release (Phase 4 stage 9-equivalent path).
    r2 = c.get(
        f"/csf/services/{svc_id}/assessments/latest",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r2.status_code == 403


@pytest.mark.unit
def test_create_assessment_rejects_non_csf_service(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    # Open a tech-debt service instead.
    r = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": "tech_debt", "title": "x"},
    )
    td_svc_id = r.json()["id"]
    r2 = c.post(
        f"/csf/services/{td_svc_id}/assessments",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r2.status_code == 404


@pytest.mark.unit
def test_catalog_subcategory_count_matches_module() -> None:
    # Defense-in-depth: the route adapter shouldn't drop subcategories.
    # The route test (test_catalog_endpoint_returns_106_subcategories)
    # asserts on the HTTP shape; this one asserts the module's truth.
    assert len(SUBCATEGORIES) == 106


# ---------------------------------------------------------------------------
# Approved-assessment write guards (issue #37)
#
# `patch_answer` refuses on APPROVED/RELEASED/DISCARDED and has since D-031.
# Three sibling routes never loaded the parent assessment at all, so the CSF
# SCORE table — the numbers the deliverable is rendered from — stayed writable
# after approval, after finalize, and after release, with no audit row naming
# who changed them.
# ---------------------------------------------------------------------------


def _approved_with_scores(c: TestClient) -> tuple[str, str, str, str]:
    """An APPROVED CSF assessment with seeded high-tier scores.

    Returns (bearer, service id, assessment id, one dimension-score id).
    """
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = _open_service(c, bearer)
    a = _new_assessment(c, bearer, svc_id)
    seeded = c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    assert seeded.status_code == 200, seeded.text
    rows = c.get(f"/csf/services/{svc_id}/profile/high", headers=h).json()["rows"]
    score_id = rows[0]["id"]
    approved = c.post(f"/csf/assessments/{a['id']}/approve", headers=h)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    return bearer, svc_id, a["id"], score_id


@pytest.mark.unit
def test_dimension_scores_are_not_writable_once_approved(app_client) -> None:
    """The scores the client-facing report is built from must freeze on approve.

    `patch_dimension_score` never loaded `CsfAssessment`, so it could not see
    the status. An admin could rewrite a released assessment's scores and get a
    200, while `clients.py` serves APPROVED/RELEASED assessments to the client
    dashboard — so the delivered PDF and the live dashboard would disagree with
    nothing recording why.
    """
    c = app_client
    bearer, _, _, score_id = _approved_with_scores(c)
    r = c.patch(
        f"/csf/dimension-scores/{score_id}",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"governance": 0, "policy": 0},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "assessment_locked"


@pytest.mark.unit
def test_patching_a_dimension_score_writes_an_audit_row(app_client) -> None:
    """Its sibling `patch_answer` audits every edit. This route did not, so a
    change to the scores had no actor and no timestamp anywhere."""
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = _open_service(c, bearer)
    _new_assessment(c, bearer, svc_id)
    c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    rows = c.get(f"/csf/services/{svc_id}/profile/high", headers=h).json()["rows"]
    score_id = rows[0]["id"]

    ok = c.patch(f"/csf/dimension-scores/{score_id}", headers=h, json={"governance": 2})
    assert ok.status_code == 200, ok.text

    from app.models.audit_entry import AuditEntry

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as check:
        entry = check.execute(
            select(AuditEntry).where(AuditEntry.action == "csf.dimension_score.updated")
        ).scalar_one()
        assert str(entry.target_id) == score_id
        assert entry.actor_user_id is not None


@pytest.mark.unit
def test_gap_actions_are_not_writable_once_approved(app_client) -> None:
    """POA&M annotations ride the same deliverable, so they freeze with it."""
    c = app_client
    bearer, svc_id, _, _ = _approved_with_scores(c)
    code = SUBCATEGORIES[0].code
    r = c.put(
        f"/csf/services/{svc_id}/gap-actions/{code}",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"owner": "someone"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "assessment_locked"


@pytest.mark.unit
def test_profiles_cannot_be_seeded_into_an_approved_assessment(app_client) -> None:
    """Seeding writes new CsfDimensionScore rows, which is a mutation of a
    frozen assessment however additive it looks."""
    c = app_client
    bearer, svc_id, _, _ = _approved_with_scores(c)
    r = c.post(
        f"/csf/services/{svc_id}/profiles/seed",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"tiers": ["moderate"]},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "assessment_locked"


@pytest.mark.unit
def test_a_discarded_assessment_says_so_rather_than_claiming_approval(app_client) -> None:
    """DISCARDED is reachable only through `patch_dimension_score`, which loads
    by `row.assessment_id`; `_latest_assessment` filters it out for the other
    two callers. It gets its own message because telling someone a thrown-away
    assessment is "locked after approval" describes the opposite of what
    happened, and sends them looking for an approval nobody made."""
    c = app_client
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = _open_service(c, bearer)
    a = _new_assessment(c, bearer, svc_id)
    c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    rows = c.get(f"/csf/services/{svc_id}/profile/high", headers=h).json()["rows"]
    score_id = rows[0]["id"]

    discarded = c.post(f"/csf/assessments/{a['id']}/discard", headers=h)
    assert discarded.status_code == 200, discarded.text

    r = c.patch(f"/csf/dimension-scores/{score_id}", headers=h, json={"governance": 2})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "assessment_discarded"

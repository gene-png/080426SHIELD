"""Client-facing ATT&CK coverage dashboard endpoint (D-035).

GET /clients/{client_id}/attack/{service_id}/dashboard returns the released
coverage rollup + per-technique rows to the CLIENT, gated on the service having a
released deliverable (reusing the value-summary release gate, NOT the assessment
status). Walks the same admin approve -> finalize -> release preamble the other
attack tests use, then reads the dashboard as the client.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.storage.local import LocalFilesystemStorage


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "shield-attack-dash.db"
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


def _seed_finalize_release(c: TestClient, bearer: str, *, release: bool) -> str:
    """Open service, mark 5 techniques covered, approve, finalize, optionally
    release. Returns the service id."""
    svc_id = c.post(
        "/attack/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": "attack_coverage", "title": "Atlas - ATT&CK Coverage"},
    ).json()["id"]
    assessment = c.post(
        f"/attack/services/{svc_id}/assessments",
        headers={"Authorization": f"Bearer {bearer}"},
    ).json()
    for cov in assessment["coverage"][:5]:
        c.patch(
            f"/attack/coverage/{cov['id']}",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"status": "covered"},
        )
    c.post(
        f"/attack/assessments/{assessment['id']}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    deliv_id = c.post(
        f"/attack/services/{svc_id}/deliverables/finalize",
        headers={"Authorization": f"Bearer {bearer}"},
    ).json()["id"]
    if release:
        rel = c.post(
            f"/attack/deliverables/{deliv_id}/release",
            headers={"Authorization": f"Bearer {bearer}"},
        )
        assert rel.status_code == 200, rel.text
    return svc_id


@pytest.mark.unit
def test_dashboard_released_returns_rollup_and_techniques(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_finalize_release(c, bearer_admin, release=True)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/attack/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rollup"]["covered"] == 5
    assert body["rollup"]["total_evaluated"] == 5  # 5 covered + 0 partial + 0 gap
    covered = [t for t in body["techniques"] if t["status"] == "covered"]
    assert len(covered) == 5
    # Every evaluated technique carries a resolved catalog name + tactic.
    assert all(t["name"] and t["tactic_name"] for t in covered)
    assert body["deliverable_version"] == 1


@pytest.mark.unit
def test_dashboard_unreleased_is_404_typed(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_finalize_release(c, bearer_admin, release=False)  # finalized, NOT released

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/attack/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["reason"] == "dashboard_not_released"


@pytest.mark.unit
def test_dashboard_cross_tenant_is_404(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    # A second client on a different domain auto-provisions its own tenant (D-034).
    other = _register(c, "outsider@other-co.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_other = other["tokens"]["access_token"]
    tenant1_client_id = client["user"]["client_id"]

    svc_id = _seed_finalize_release(c, bearer_admin, release=True)

    # The outsider (own tenant) cannot read tenant 1's dashboard.
    c.headers["X-Client-Id"] = other["user"]["client_id"]
    r = c.get(
        f"/clients/{tenant1_client_id}/attack/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_other}"},
    )
    assert r.status_code == 404


@pytest.mark.unit
def test_attack_release_flips_the_assessment_to_released(app_client) -> None:
    """W4 for ATT&CK. Same defect as the other three: the only writer of
    RELEASED in the repo was `seed_demo.py`, so the status was unreachable
    through the product and every reader keyed on it was effectively dead.
    """
    c = app_client
    bearer = _register(c, "w4-attack-parent@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = _seed_finalize_release(c, bearer, release=True)

    latest = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h)
    assert latest.status_code == 200, latest.text
    assert latest.json()["status"] == "released"


@pytest.mark.unit
def test_client_dashboard_withholds_the_same_rows_the_released_pdf_does(app_client) -> None:
    """#102, found by the §14 audit of the branch that added it.

    `finalize_attack_deliverable` and `heatmap` were wired to withhold unbacked
    claims; **this route was not**, and it is the one the CLIENT reads. The two
    surfaces are gated to appear together -- this dashboard is visible exactly
    when the released PDF is -- so one assessment could hand a client a PDF
    saying 0.0% and an in-app dashboard saying 100%.

    The miss came from checking one function instead of the file.
    `_attack_uncovered_total` in the same module carries a comment reading "If
    this ever starts reading `covered`, `partial` or `coverage_pct`, it MUST
    pass them" -- and `attack_dashboard`, 240 lines below, reads all three.
    Grepping the call sites of the function just changed finds every copy that
    went through it and misses every other caller in the same file.

    The existing dashboard tests could not catch this: they build covered rows
    through `PATCH /attack/coverage/{id}`, which takes authorship and stamps the
    citations confirmed, so no fixture in that file can produce a pending row.

    The state written here IS reachable in production: Run-AI leaves inferred
    citations on a draft, approval does not stamp them (that was the separate
    decision D-056 deliberately did NOT take), and migration 0045 only
    grandfathers rows whose column is NULL.
    """
    from sqlalchemy.orm import Session as _Session

    from app.models.attack_assessment import AttackCoverage

    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_finalize_release(c, bearer_admin, release=True)

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with _Session(engine) as db:
        rows = db.query(AttackCoverage).filter(AttackCoverage.status == "covered").all()
        assert rows, "fixture produced no covered rows"
        # The shape a Run-AI leaves when every citation had to be INFERRED: the
        # tool is applied, and nobody has vouched for it.
        for r in rows:
            r.detection_tools = ["CrowdStrike Falcon"]
            r.unconfirmed_citations = [
                {
                    "tool": "CrowdStrike Falcon",
                    "cited": "CrowdStrike",
                    "reason": "substring",
                    "field": "detection_tools",
                    "cleared_at": None,
                }
            ]
        withheld = len(rows)
        db.commit()

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/attack/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    rollup = r.json()["rollup"]

    assert rollup["covered"] == 0, (
        "the client dashboard counted an unconfirmed claim as covered while the "
        "released PDF withheld it -- two numbers for one assessment"
    )
    assert rollup["pending_review"] == withheld, (
        "withholding without saying how much was withheld narrows the denominator "
        "silently, which is the false assurance the rule exists to prevent"
    )
    touched = [t for t in rollup["by_tactic"] if t["pending_review"] > 0]
    assert touched, "the per-tactic breakdown dropped the pending count"

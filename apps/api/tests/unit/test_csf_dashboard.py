"""Client-facing NIST CSF 2.0 dashboard endpoint.

GET /clients/{client_id}/csf/{service_id}/dashboard returns the per-function
current-vs-target maturity rollup to the CLIENT, gated on the service having a
released deliverable — the same contract the other four dashboards use.

CSF was the only service without one: `dashboardPathFor` returned null for
`nist_csf`, so a client could see a CSF gap count on their home page and had no
way to open the results.
"""

from __future__ import annotations

import os
import uuid
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
    db_path = tmp_path / "shield-csf-dash.db"
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


def _seed_release(c: TestClient, bearer: str, *, score_tier: int = 2, release: bool = True) -> str:
    """Open a CSF service, score every subcategory, approve, finalize, release."""
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = c.post(
        "/csf/services", headers=h, json={"kind": "nist_csf", "title": "Atlas - CSF"}
    ).json()["id"]
    assessment = c.post(f"/csf/services/{svc_id}/assessments", headers=h).json()
    for ans in assessment["answers"]:
        c.patch(f"/csf/answers/{ans['id']}", headers=h, json={"maturity_tier": score_tier})
    c.post(f"/csf/assessments/{assessment['id']}/approve", headers=h)
    fin = c.post(f"/csf/services/{svc_id}/deliverables/finalize", headers=h)
    assert fin.status_code == 201, fin.text
    if release:
        rel = c.post(f"/csf/deliverables/{fin.json()['id']}/release", headers=h)
        assert rel.status_code == 200, rel.text
    return svc_id


@pytest.mark.unit
def test_csf_dashboard_released_returns_functions(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, admin["tokens"]["access_token"], score_tier=2)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/csf/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Tier 2 of 4 -> 50%. Default target tier 3 of 4 -> 75%.
    assert body["current_pct"] == 50.0
    assert body["target_pct"] == 75.0
    assert body["coverage_pct"] == 100.0
    # CSF 2.0 has six functions: Govern, Identify, Protect, Detect, Respond, Recover.
    assert len(body["functions"]) == 6
    fn = body["functions"][0]
    assert fn["current_pct"] == 50.0
    assert fn["target_pct"] == 75.0
    assert fn["gap_pct"] == 25.0
    assert body["largest_gap_pct"] == 25.0
    assert body["largest_gap_function"] is not None


@pytest.mark.unit
def test_csf_dashboard_unreleased_is_a_typed_404(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, admin["tokens"]["access_token"], release=False)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/csf/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["reason"] == "dashboard_not_released"


@pytest.mark.unit
def test_csf_dashboard_states_the_true_gap_total_not_just_the_shown_slice(app_client) -> None:
    """`top_gaps` is truncated; `total_gap_count` is not.

    #75 is open because the ZT exporter renders a 20-item slice with the real
    count nowhere on the page, so a client reads 20 of 37 remediation items with
    no statement that anything was omitted. The payload has to carry both, or
    the UI cannot disclose it even if it wants to.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    client_id = client["user"]["client_id"]

    # Tier 1 everywhere against a target of 3 makes every subcategory a gap.
    svc_id = _seed_release(c, admin["tokens"]["access_token"], score_tier=1)

    c.headers["X-Client-Id"] = client_id
    body = c.get(
        f"/clients/{client_id}/csf/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    ).json()

    assert body["total_gap_count"] > len(
        body["top_gaps"]
    ), "the fixture must actually exercise truncation, or this proves nothing"
    assert sum(f["gap_count"] for f in body["functions"]) == body["total_gap_count"]


@pytest.mark.unit
def test_csf_dashboard_uses_the_clients_intake_target_not_the_engine_default(app_client) -> None:
    """The #73 lesson, applied before the same defect can be built.

    The ZT exporter has computed gaps against a hardcoded 3 for the life of the
    repo while the client had chosen 4 at intake, so the delivered document
    listed a different gap set than the consultant approved and a stored target
    of 2 printed as 3. This asserts the dashboard reads the intake choice, and
    that `target_tier_source` distinguishes a real choice from a fallback.
    """
    import uuid as _uuid

    from sqlalchemy import create_engine as _ce
    from sqlalchemy.orm import sessionmaker as _sm

    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    client_id = client["user"]["client_id"]
    # score_tier=3, NOT 2: at tier 2 every subcategory is a gap against both
    # target 3 and target 4, so the totals match and a `>=` assertion holds by
    # equality whether or not the endpoint reads the client's tier. At tier 3
    # the count moves 0 -> 106, which is the thing being claimed.
    svc_id = _seed_release(c, admin["tokens"]["access_token"], score_tier=3)

    c.headers["X-Client-Id"] = client_id
    before = c.get(
        f"/clients/{client_id}/csf/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    ).json()
    assert before["target_tier"] == 3
    assert before["target_tier_source"] == "default"

    # Attach a source request carrying the client's chosen tier of 4.
    from app.models.service import Service as _Service
    from app.models.service_request import ServiceRequest as _SR

    eng = _ce(os.environ["DATABASE_URL"], future=True)
    with _sm(bind=eng, future=True)() as s:
        svc = s.get(_Service, _uuid.UUID(svc_id))
        sr = _SR(
            client_id=svc.client_id,
            service_type="nist_csf",
            requested_by=svc.opened_by,
            csf_target_tier=4,
        )
        s.add(sr)
        s.flush()
        svc.source_request_id = sr.id
        s.commit()

    after = c.get(
        f"/clients/{client_id}/csf/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    ).json()
    assert after["target_tier"] == 4, "the client's intake choice was ignored"
    assert after["target_tier_source"] == "client"
    assert after["target_pct"] == 100.0
    # The gap set MOVES — the whole point of reading the client's tier. At tier
    # 3 against target 3 nothing is a gap; against target 4 everything is.
    assert before["total_gap_count"] == 0, before["total_gap_count"]
    assert after["total_gap_count"] > 0, after["total_gap_count"]


@pytest.mark.unit
def test_csf_dashboard_cross_tenant_is_404(app_client) -> None:
    """Another tenant's released CSF service is not readable.

    Every other dashboard has this test; CSF did not, so the tenant check was
    correct and unproven.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    svc_id = _seed_release(c, admin["tokens"]["access_token"])

    other = uuid.uuid4()
    c.headers["X-Client-Id"] = str(other)
    r = c.get(
        f"/clients/{other}/csf/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    )
    assert r.status_code == 404, r.text


@pytest.mark.unit
def test_admin_previews_a_finalized_but_unreleased_csf_dashboard(app_client) -> None:
    """The preview path — the ONLY path that sets `released=False`.

    It had no test at all, and (until this change) no link in the product
    either, so the whole admin-preview branch was unreachable and unproven.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    client_id = client["user"]["client_id"]
    bearer_admin = admin["tokens"]["access_token"]

    svc_id = _seed_release(c, bearer_admin, release=False)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/csf/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["released"] is False

    # And the client still cannot, on the same assessment.
    rc = c.get(
        f"/clients/{client_id}/csf/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    )
    assert rc.status_code == 404, rc.text


@pytest.mark.unit
def test_csf_dashboard_names_an_unassessed_function_rather_than_ranking_it(
    app_client,
) -> None:
    """A function with no answers must say so.

    Its `gap_pct` is computed against 0, so it sorts to the TOP of a list the UI
    heads "largest move required" — with `0 gaps` beside it, because unscored
    subcategories are not gaps. Without a label, a client reads their worst
    function as one that was never scored.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    client_id = client["user"]["client_id"]
    bearer = admin["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}

    svc_id = c.post(
        "/csf/services", headers=h, json={"kind": "nist_csf", "title": "Atlas - CSF"}
    ).json()["id"]
    assessment = c.post(f"/csf/services/{svc_id}/assessments", headers=h).json()
    # Score everything EXCEPT the Govern function.
    for ans in assessment["answers"]:
        if ans["subcategory_code"].startswith("GV"):
            continue
        c.patch(f"/csf/answers/{ans['id']}", headers=h, json={"maturity_tier": 2})
    c.post(f"/csf/assessments/{assessment['id']}/approve", headers=h)
    fin = c.post(f"/csf/services/{svc_id}/deliverables/finalize", headers=h)
    c.post(f"/csf/deliverables/{fin.json()['id']}/release", headers=h)

    c.headers["X-Client-Id"] = client_id
    body = c.get(
        f"/clients/{client_id}/csf/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    ).json()

    govern = next(f for f in body["functions"] if f["code"] == "GV")
    assert govern["current_tier"] is None
    assert govern["current_pct"] is None
    assert govern["current_label"] == "Unscored", govern
    assert govern["answered_count"] == 0
    assert govern["gap_count"] == 0
    # And the headline does NOT call it the largest gap, because it has none.
    assert body["largest_gap_function"] != govern["name"]

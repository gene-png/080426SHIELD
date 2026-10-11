"""#85: the self-assessment SUBMIT routes refuse a target below the floor.

Intake has refused Tier/Stage 1 since #406 with a typed `{reason, message}`
(D-016). The two self-assessment submit routes also write the engagement target
(`ServiceRequest.csf_target_tier` / `.zt_target_stage`) and accepted 1: CSF had
no range check at all behind a schema `ge=1, le=4`, and ZT guarded `1 <= stage`.
A stored 1 then made every gap list vacuously empty ("0 gap(s) at target T1").

Both ends are checked IN THE ROUTE, as at intake, never by a schema bound: a
`Field(ge=...)` refusal arrives as a `schema_*` reason the web layer withholds
by design, so the client would read a bare generic fallback. Every refusal here
is asserted by its reason AND its sentence, and every one is followed by a
positive control, so a route that refused everything could not pass.
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

# The floor sentences, from the SPEC (the intake copy approved on #406), not
# from the helper under test.
CSF_FLOOR = (
    "Tier 1 is where an organization starts, not a target to aim at. " "Choose Tier 2 or higher."
)
ZT_FLOOR = (
    "Stage 1 is where an organization starts, not a target to aim at. " "Choose Stage 2 or higher."
)


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    url = f"sqlite:///{tmp_path / 'shield-target-floor.db'}"
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

    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    seed = TestSession()
    tenant = _Client(legal_name=None)
    seed.add(tenant)
    seed.flush()
    seed.add(_ClientDomain(client_id=tenant.id, domain="example.com"))
    seed.commit()
    seed.close()

    with TestClient(app) as c:
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


def _client_with(c: TestClient, *requests: dict) -> tuple[dict, dict]:
    """Admin first, then the client runs intake. Returns headers + intake state."""
    _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    h = {"Authorization": f"Bearer {client['tokens']['access_token']}"}
    r = c.post(
        "/intake/submit",
        headers=h,
        json={"client": {"legal_name": "Atlas Defense Solutions"}, "service_requests": requests},
    )
    assert r.status_code == 200, r.text
    return h, r.json()


def _service_id(state: dict, service_type: str) -> str:
    sr = next(s for s in state["service_requests"] if s["service_type"] == service_type)
    assert sr["fulfilled_service_id"] is not None, "request was not auto-provisioned"
    return sr["fulfilled_service_id"]


def _reset_to_draft(table: str) -> None:
    """A submit flips the status, and the status check runs BEFORE the target
    guard; put it back so the next submit reaches the code under test."""
    import sqlalchemy as sa

    eng = sa.create_engine(os.environ["DATABASE_URL"], future=True)
    with eng.begin() as conn:
        conn.execute(sa.text(f"UPDATE {table} SET status = 'DRAFT'"))  # noqa: S608


def _refusal(r) -> dict:
    assert r.status_code == 422, r.text
    err = r.json()["error"]
    assert not str(err.get("reason", "")).startswith(
        "schema_"
    ), f"refused by a schema bound, not by the route's typed guard: {err}"
    return err


# --------------------------------------------------------------------- CSF


def _csf(c: TestClient) -> tuple[dict, str]:
    h, state = _client_with(
        c, {"service_type": "nist_csf", "csf_target_tier": 3, "csf_profile": "MOD"}
    )
    svc_id = _service_id(state, "nist_csf")
    assert c.get(f"/csf/services/{svc_id}/self-assessment", headers=h).status_code == 200
    return h, svc_id


def _csf_submit(c: TestClient, h: dict, svc_id: str, tier: object):
    return c.post(
        f"/csf/services/{svc_id}/self-assessment/submit", headers=h, json={"target_tier": tier}
    )


@pytest.mark.unit
def test_csf_submit_refuses_tier_1_and_keeps_the_stored_target(app_client) -> None:
    c = app_client
    h, svc_id = _csf(c)

    err = _refusal(_csf_submit(c, h, svc_id, 1))
    assert err["reason"] == "target_tier_out_of_range", err
    assert err["message"] == CSF_FLOOR, err

    # Nothing was written: still a draft, still the intake tier.
    a = c.get(f"/csf/services/{svc_id}/self-assessment", headers=h).json()
    assert a["status"] == "draft", a["status"]
    assert a["client_target_tier"] == 3, a["client_target_tier"]

    ok = _csf_submit(c, h, svc_id, 2)
    assert ok.status_code == 200, ok.text
    assert ok.json()["client_target_tier"] == 2


@pytest.mark.unit
@pytest.mark.parametrize("tier", [0, -5])
def test_csf_submit_refuses_a_tier_below_the_ladder_with_a_typed_reason(app_client, tier) -> None:
    c = app_client
    h, svc_id = _csf(c)
    err = _refusal(_csf_submit(c, h, svc_id, tier))
    assert err["reason"] == "target_tier_out_of_range", err
    assert err["message"] == f"NIST CSF 2.0 has tiers 1-4; {tier} is not one of them.", err


@pytest.mark.unit
def test_csf_submit_refuses_a_tier_above_the_ladder_with_a_typed_reason(app_client) -> None:
    c = app_client
    h, svc_id = _csf(c)
    err = _refusal(_csf_submit(c, h, svc_id, 5))
    assert err["reason"] == "target_tier_out_of_range", err
    assert err["message"] == "NIST CSF 2.0 has tiers 1-4; 5 is not one of them.", err

    ok = _csf_submit(c, h, svc_id, 4)
    assert ok.status_code == 200, ok.text
    assert ok.json()["client_target_tier"] == 4


@pytest.mark.unit
def test_csf_submit_without_a_target_still_submits(app_client) -> None:
    """The field is optional: no target means keep the one on file."""
    c = app_client
    h, svc_id = _csf(c)
    r = c.post(f"/csf/services/{svc_id}/self-assessment/submit", headers=h, json={})
    assert r.status_code == 200, r.text
    assert r.json()["client_target_tier"] == 3


# ---------------------------------------------------------------------- ZT


def _zt(c: TestClient, service_type: str) -> tuple[dict, str]:
    h, state = _client_with(c, {"service_type": service_type, "zt_target_stage": 3})
    svc_id = _service_id(state, service_type)
    assert c.get(f"/zt/services/{svc_id}/self-assessment", headers=h).status_code == 200
    return h, svc_id


def _zt_submit(c: TestClient, h: dict, svc_id: str, stage: object):
    return c.post(
        f"/zt/services/{svc_id}/self-assessment/submit", headers=h, json={"target_stage": stage}
    )


@pytest.mark.unit
@pytest.mark.parametrize("service_type", ["zero_trust_cisa", "zero_trust_dod"])
def test_zt_submit_refuses_stage_1_and_keeps_the_stored_target(app_client, service_type) -> None:
    c = app_client
    h, svc_id = _zt(c, service_type)

    err = _refusal(_zt_submit(c, h, svc_id, 1))
    assert err["reason"] == "target_stage_out_of_range", err
    assert err["message"] == ZT_FLOOR, err

    a = c.get(f"/zt/services/{svc_id}/self-assessment", headers=h).json()
    assert a["status"] == "draft", a["status"]
    assert a["client_target_stage"] == 3, a["client_target_stage"]

    _reset_to_draft("zt_assessments")
    ok = _zt_submit(c, h, svc_id, 2)
    assert ok.status_code == 200, ok.text
    assert ok.json()["client_target_stage"] == 2


@pytest.mark.unit
@pytest.mark.parametrize("stage", [0, -5, 5])
def test_zt_submit_refuses_a_stage_off_the_ladder_with_a_typed_reason(app_client, stage) -> None:
    """Below 1 and above 4 used to be the schema's `ge=1, le=4`, refused with a
    `schema_*` reason; the route's own ceiling sentence covers them now."""
    c = app_client
    h, svc_id = _zt(c, "zero_trust_cisa")
    err = _refusal(_zt_submit(c, h, svc_id, stage))
    assert err["reason"] == "target_stage_out_of_range", err
    assert "has stages 1-4" in err["message"], err

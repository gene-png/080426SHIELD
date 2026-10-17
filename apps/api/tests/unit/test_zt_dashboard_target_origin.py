"""#1343: the client's ZT dashboard names every applied per-capability target
whose origin is not recorded, so the web can render the approved line beside
the percentages those targets feed (placement approved at #736 6225462107).

The state: a released assessment whose per-capability targets were stored
before migration 0076 (origin NULL). The admin PATCH stamps `consultant`, so
this test clears it on one row, which is exactly what every pre-0076 row
looks like. The expected codes are written from that setup.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from tests.unit.test_zt_dashboard import (  # noqa: F401  (fixture)
    _register,
    _seed_release,
    app_client,
)

pytestmark = pytest.mark.unit


def _clear_origin_of_one(svc_id: str) -> str:
    from app.models.zt_assessment import ZtAnswer, ZtAssessment

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as s:
        a_id = s.execute(
            select(ZtAssessment.id).where(ZtAssessment.service_id == uuid.UUID(svc_id))
        ).scalar_one()
        rows = (
            s.execute(
                select(ZtAnswer)
                .where(ZtAnswer.assessment_id == a_id)
                .order_by(ZtAnswer.capability_code)
            )
            .scalars()
            .all()
        )
        assert rows and all(r.target_source == "consultant" for r in rows), "setup"
        rows[0].target_source = None  # stored before 0076
        s.commit()
        return rows[0].capability_code


def _dashboard(c, client: dict, svc_id: str) -> dict:
    client_id = client["user"]["client_id"]
    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_the_dashboard_names_the_target_whose_origin_is_not_recorded(
    app_client,  # noqa: F811
) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    svc_id = _seed_release(c, admin["tokens"]["access_token"], release=True, target_stage=3)
    code = _clear_origin_of_one(svc_id)

    assert _dashboard(c, client, svc_id)["unrecorded_target_codes"] == [code]


def test_consultant_set_targets_are_not_named(app_client) -> None:  # noqa: F811
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    svc_id = _seed_release(c, admin["tokens"]["access_token"], release=True, target_stage=3)

    assert _dashboard(c, client, svc_id)["unrecorded_target_codes"] == []

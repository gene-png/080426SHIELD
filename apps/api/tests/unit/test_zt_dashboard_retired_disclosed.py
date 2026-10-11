"""The client ZT dashboard carries the retired-answer disclosure (#914, in #839).

Migration 0064 retires six DoD rows that a RELEASED assessment may have
answered, so the client's coverage reads x/45 where it read x/50. The
consultant workspace, the self-assessment and the three files already say why
(`retired_answers_note`, #881); the client dashboard said nothing. The advisor
ruled it ships with 0064 (#736 comment 6048561596).

This pins the DATA, through the endpoint the client's dashboard reads. The
sentence is the approved retired-rows copy, reused verbatim (decision 4, the
DoD source per 5984022081), copied here from that approval, not from the code.
Rendering it on the dashboard waits on the advisor's sign-off of the plan.
"""

from __future__ import annotations

import pytest

from tests.unit.test_zt_dashboard import (  # noqa: F401  (fixture)
    _register,
    _seed_release,
    app_client,
)
from tests.unit.test_zt_retired_answers_disclosed import _keep

pytestmark = pytest.mark.unit

ONE = (
    "1 recorded answer belongs to a row that the DoD Zero Trust Execution Roadmap "
    "does not have, so it is not scored."
)


def _dashboard(c, kind: str, retired: list[tuple[str, int | None, str | None]]) -> dict:
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    svc_id = _seed_release(c, bearer, release=True, target_stage=None, kind=kind)
    latest = c.get(
        f"/zt/services/{svc_id}/assessments/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert latest.status_code == 200, latest.text
    if retired:
        _keep(latest.json()["id"], retired)
    client_id = client["user"]["client_id"]
    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_a_released_dod_dashboard_states_its_retired_answers(app_client) -> None:  # noqa: F811
    body = _dashboard(app_client, "zero_trust_dod", [("DOD.NET.05", 2, None)])
    assert body["retired_answers"] == 1
    assert body["retired_answers_note"] == ONE


def test_a_dashboard_with_none_says_nothing(app_client) -> None:  # noqa: F811
    body = _dashboard(app_client, "zero_trust_dod", [])
    assert body["retired_answers"] == 0
    assert body["retired_answers_note"] is None

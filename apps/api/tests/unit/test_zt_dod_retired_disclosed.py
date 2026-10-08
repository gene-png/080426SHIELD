"""Answers kept on rows the DoD catalog no longer has are disclosed (#839).

Migration 0064 KEEPS the answers on the six DoD rows the 2025 roadmap does not
have (decision 4, option B), as 0063 does for CISA. The approved sentence names
the source "the DoD Zero Trust Execution Roadmap" (#736, approved with the PR 3
plan). The seeded row is what 0064 leaves; the check goes through the GET a
consultant's workspace and the client's self-assessment both read.
"""

from __future__ import annotations

import pytest

from tests.unit.test_zt_acceptance import (  # noqa: F401  (fixture)
    _register,
    app_client,
)
from tests.unit.test_zt_retired_answers_disclosed import _keep, _latest

pytestmark = pytest.mark.unit

ONE = (
    "1 recorded answer belongs to a row that the DoD Zero Trust Execution Roadmap "
    "does not have, so it is not scored."
)


def test_a_retired_dod_answer_is_disclosed_with_the_dod_source(app_client) -> None:  # noqa: F811
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = c.post(
        "/zt/services", headers=h, json={"kind": "zero_trust_dod", "title": "ZT"}
    ).json()["id"]
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h).json()
    assert len(a["answers"]) == 45  # the 2025 roadmap's capabilities
    _keep(a["id"], [("DOD.NET.05", 2, None)])  # a retired v1 row
    body = _latest(c, h, svc_id)
    assert body["retired_answers"] == 1
    assert body["retired_answers_note"] == ONE

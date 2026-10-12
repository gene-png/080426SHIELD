"""`scripts/measure_evidence_blast_radius.py` measures the version, and the target,
that a client surface actually reads (#1090 review, findings 1 and 3).

`zt_dashboard` renders the parent of the latest RELEASED deliverable
(`_deliverable_parent`) against the target that deliverable was FROZEN with
(`_frozen_or_live_target`, #209), not the live intake target. A measurement
that read the live target would report a released client's gaps against a
number the client never saw.

Every row is written by a product route: the intake target through the ORM
exactly as `test_frozen_engagement_target.py` does (its own reason: the
`ServiceRequest` row is the intake writer's), scores through
`PATCH /zt/answers/{id}`, approval, `POST .../deliverables/finalize` (which
freezes the target and stamps `parent_version`) and `POST .../release`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import measure_evidence_blast_radius as m
from tests.unit.test_frozen_engagement_target import (  # noqa: F401  (fixture)
    _register,
    _set_intake_target,
    _zt_finalize_release,
    _zt_service,
    app_client,
)

pytestmark = pytest.mark.unit

_API = Path(__file__).resolve().parents[2]
_SCRIPT = _API / "scripts" / "measure_evidence_blast_radius.py"


def _run(url: str) -> dict:
    env = {**os.environ, "DATABASE_URL": url}
    r = subprocess.run(  # noqa: S603 -- this interpreter, the repo's own script
        [sys.executable, str(_SCRIPT)], cwd=_API, env=env, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout.split(m.JSON_MARKER, 1)[1])


def test_the_released_version_is_measured_against_its_FROZEN_target(
    app_client,  # noqa: F811
) -> None:
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc = _zt_service(c, bearer)
    _set_intake_target(svc, zt_stage=2)
    a = c.post(f"/zt/services/{svc}/assessments", headers=h).json()
    for ans in a["answers"]:
        assert c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"maturity_stage": 4}).is_success
    assert c.post(f"/zt/assessments/{a['id']}/approve", headers=h).is_success
    _zt_finalize_release(c, bearer, svc)  # freezes target 2, stamps parent_version
    _set_intake_target(svc, zt_stage=4)  # the LIVE target moves after release
    # A v2 draft opens after the release: a version no client surface reads.
    v2 = c.post(f"/zt/services/{svc}/assessments", headers=h).json()
    assert v2["id"] != a["id"]
    n = len(a["answers"])
    assert n > 0

    report = _run(os.environ["DATABASE_URL"])
    headline = report["zt_assessments"]["surfaced"]["by_status"]

    # Every CISA capability scored 4 reaches 4, so at launch each counts as
    # lowest + 1 = 2. Against the FROZEN target 2 that is no gap at all; against
    # the live target 4 it would be all n capabilities.
    assert headline["released"]["assessments_evaluated"] == 1
    assert headline["released"]["targets_frozen"] == 1
    assert headline["released"]["gaps_today"] == 0
    assert headline["released"]["gaps_launch"] == 0
    assert headline["released"]["average_stage_moves"] == 1
    # The v2 draft is not a surfaced version: absent from the headline, present
    # in the all-versions line.
    assert headline["draft"]["assessments_evaluated"] == 0
    every = report["zt_assessments"]["all_versions"]["by_status"]
    assert every["draft"]["assessments_evaluated"] == 1
    assert every["released"]["assessments_evaluated"] == 1
    answers = report["zt_answers"]["surfaced"]["by_status"]["released"]
    assert answers["stage_moves"] == n
    assert report["zt_assessments"]["parents_unresolved"] == []

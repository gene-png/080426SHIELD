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

CSF is different (round-2 review): `csf_dashboard` reads `CsfAnswer`, which
no proposed rule touches, and every reader of the Playbook rows --
`enterprise_subcategories`, `export_playbook` -- takes
`routes.csf._latest_assessment`, the latest NON-DISCARDED version. So CSF's
headline is that version, released or not.

The database URL is built here from `tmp_path` (the imported fixture's own
file name) and checked against the file, rather than read back from the
environment the fixture happens to set.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

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


def _url(tmp_path: Path) -> str:
    """The fixture's database, named explicitly (its file name is the one
    `test_frozen_engagement_target.app_client` creates under this tmp_path)."""
    db = tmp_path / "shield-frozen-target.db"
    assert db.is_file(), db
    return f"sqlite:///{db}"


def _run_full(url: str) -> tuple[dict, str]:
    env = {**os.environ, "DATABASE_URL": url}
    r = subprocess.run(  # noqa: S603 -- this interpreter, the repo's own script
        [sys.executable, str(_SCRIPT)], cwd=_API, env=env, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr
    table, payload = r.stdout.split(m.JSON_MARKER, 1)
    return json.loads(payload), table


def _run(url: str) -> dict:
    return _run_full(url)[0]


def _released_zt_on_four(c, h: dict, bearer: str) -> tuple[str, dict]:
    """A CISA service, every answer at 4, approved, finalized and released."""
    svc = _zt_service(c, bearer)
    _set_intake_target(svc, zt_stage=2)
    a = c.post(f"/zt/services/{svc}/assessments", headers=h).json()
    for ans in a["answers"]:
        assert c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"maturity_stage": 4}).is_success
    assert c.post(f"/zt/assessments/{a['id']}/approve", headers=h).is_success
    _zt_finalize_release(c, bearer, svc)  # freezes target 2, stamps parent_version
    return svc, a


def test_the_released_version_is_measured_against_its_FROZEN_target(
    app_client, tmp_path  # noqa: F811
) -> None:
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc, a = _released_zt_on_four(c, h, bearer)
    _set_intake_target(svc, zt_stage=4)  # the LIVE target moves after release
    # A v2 draft opens after the release: a version no client surface reads.
    v2 = c.post(f"/zt/services/{svc}/assessments", headers=h).json()
    assert v2["id"] != a["id"]
    n = len(a["answers"])
    assert n > 0

    report = _run(_url(tmp_path))
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


def test_a_released_deliverable_with_no_parent_version_is_listed_and_flagged(
    app_client, tmp_path  # noqa: F811
) -> None:
    """The pre-0041 shape: a released deliverable whose `parent_version` is
    NULL. Writer: finalize before migration 0041, which nothing backfills for a
    multi-version service (#59). The dashboard refuses it
    (`_unresolved_parent`), so no ZT version is surfaced: it is LISTED, and the
    headline's zeros are FLAGGED rather than reading as "nothing moves"."""
    from app.models.deliverable import Deliverable

    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc, _a = _released_zt_on_four(c, h, bearer)
    url = _url(tmp_path)
    engine = create_engine(url, future=True)
    with Session(engine) as db:
        db.execute(
            update(Deliverable)
            .where(Deliverable.service_id == uuid.UUID(svc))
            .values(parent_version=None)
        )
        db.commit()
    engine.dispose()

    report, table = _run_full(url)
    unresolved = report["zt_assessments"]["parents_unresolved"]
    assert [u["service_id"] for u in unresolved] == [svc]
    headline = report["zt_assessments"]["surfaced"]["by_status"]
    assert headline["released"]["assessments_evaluated"] == 0
    assert (
        report["zt_assessments"]["all_versions"]["by_status"]["released"]["assessments_evaluated"]
        == 1
    )
    assert "NO SURFACED VERSION (Zero Trust)" in table
    assert report["surfaced_versions"]["zt"] == 0


def _csf_seed_and_tick(c, h: dict, svc: str, ticked: int) -> None:
    """Writers: `seed_profiles` (HIGH tier, onto `_latest_assessment`) and
    `PATCH /csf/dimension-scores/{id}`: `ticked` rows ticked, all 2s."""
    assert c.post(
        f"/csf/services/{svc}/profiles/seed", headers=h, json={"tiers": ["high"]}
    ).is_success
    rows = c.get(f"/csf/services/{svc}/profile/high", headers=h).json()["rows"]
    assert len(rows) > ticked
    for row in rows[:ticked]:
        body = {
            "governance": 2,
            "policy": 2,
            "implementation": 2,
            "monitoring": 2,
            "improvement": 2,
            "has_evidence": True,
        }
        assert c.patch(f"/csf/dimension-scores/{row['id']}", headers=h, json=body).is_success


def test_the_csf_headline_is_the_version_the_playbook_reads(
    app_client, tmp_path  # noqa: F811
) -> None:
    """v1 released, v2 an open draft. The Playbook, its exports and
    `enterprise_subcategories` read `_latest_assessment`: v2. A ticked all-2
    row is L5 today and L2 at launch (R1), so v1 has one move and v2 two."""
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()["id"]
    v1 = c.post(f"/csf/services/{svc}/assessments", headers=h).json()
    _csf_seed_and_tick(c, h, svc, ticked=1)
    for ans in v1["answers"]:
        assert c.patch(f"/csf/answers/{ans['id']}", headers=h, json={"maturity_tier": 2}).is_success
    assert c.post(f"/csf/assessments/{v1['id']}/approve", headers=h).is_success
    deliv = c.post(f"/csf/services/{svc}/deliverables/finalize", headers=h)
    assert deliv.is_success, deliv.text
    assert c.post(f"/csf/deliverables/{deliv.json()['id']}/release", headers=h).is_success
    v2 = c.post(f"/csf/services/{svc}/assessments", headers=h).json()
    assert v2["id"] != v1["id"]
    _csf_seed_and_tick(c, h, svc, ticked=2)

    report, table = _run_full(_url(tmp_path))
    headline = report["csf_tier_rows"]["surfaced"]["by_status"]
    assert headline["draft"]["rows_level_moves"] == 2
    assert headline["released"]["rows_read"] == 0
    every = report["csf_tier_rows"]["all_versions"]["by_status"]
    assert every["draft"]["rows_level_moves"] == 2
    assert every["released"]["rows_level_moves"] == 1
    ent = report["csf_enterprise"]["surfaced"]["by_status"]
    assert ent["draft"]["assessments_evaluated"] == 1
    assert ent["released"]["assessments_evaluated"] == 0
    assert report["surfaced_versions"]["csf"] == 1
    assert "NO SURFACED VERSION (CSF)" not in table

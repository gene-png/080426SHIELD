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
no proposed rule touches, and the Playbook and its exports
(`export_playbook`, through `enterprise_subcategories`) take
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

    report, table = _run_full(_url(tmp_path))
    headline = report["zt_assessments"]["surfaced"]["by_status"]

    # Advisor ruling, option (a): the rule does not reach a RELEASED
    # assessment, which is scored at its stored stage. The headline counts it
    # as not moving at all.
    assert headline["released"]["assessments_evaluated"] == 1
    assert headline["released"]["targets_frozen"] == 1
    assert headline["released"]["gaps_today"] == 0
    assert headline["released"]["gaps_launch"] == 0
    assert headline["released"]["average_stage_moves"] == 0
    # The separate line: what it WOULD have moved without the freeze. Every
    # CISA capability scored 4 counts as lowest + 1 = 2; against the FROZEN
    # target 2 that is no gap at all, against the live target 4 it would be
    # all n capabilities.
    # Not the headline, so not the headline's key either (round-4 review).
    for key in ("zt_released_without_freeze_assessments", "zt_released_without_freeze_answers"):
        assert "surfaced" not in report[key]
        assert report[key]["headline"] is False
    would = report["zt_released_without_freeze_assessments"]["surfaced_if_not_frozen"]["by_status"]
    assert would["released"]["assessments_evaluated"] == 1
    assert would["released"]["targets_frozen"] == 1
    assert would["released"]["gaps_launch"] == 0
    assert would["released"]["average_stage_moves"] == 1
    would_answers = report["zt_released_without_freeze_answers"]["surfaced_if_not_frozen"][
        "by_status"
    ]
    assert would_answers["released"]["stage_moves"] == n
    # The v2 draft is not released, so it never enters the without-freeze line.
    assert would["draft"]["assessments_evaluated"] == 0
    # And that line is never labelled the headline, in either view.
    titles = [line for line in table.splitlines() if "IF NOT FROZEN" in line]
    assert len(titles) == 4, titles
    assert all("HEADLINE" not in line for line in titles), titles
    assert report["scope"]["released_without_freeze"].startswith("NOT the headline")
    # The v2 draft is not a surfaced version: absent from the headline, present
    # in the all-versions line.
    assert headline["draft"]["assessments_evaluated"] == 0
    every = report["zt_assessments"]["all_versions"]["by_status"]
    assert every["draft"]["assessments_evaluated"] == 1
    assert every["released"]["assessments_evaluated"] == 1
    answers = report["zt_answers"]["surfaced"]["by_status"]["released"]
    assert answers["stage_moves"] == 0
    assert answers["unchanged"] == n
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


def _csf_v1_released(c, h: dict) -> str:
    """A CSF service whose v1 is seeded, one row ticked, approved, finalized
    and released, through the routes."""
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()["id"]
    v1 = c.post(f"/csf/services/{svc}/assessments", headers=h).json()
    _csf_seed_and_tick(c, h, svc, ticked=1)
    for ans in v1["answers"]:
        assert c.patch(f"/csf/answers/{ans['id']}", headers=h, json={"maturity_tier": 2}).is_success
    assert c.post(f"/csf/assessments/{v1['id']}/approve", headers=h).is_success
    deliv = c.post(f"/csf/services/{svc}/deliverables/finalize", headers=h)
    assert deliv.is_success, deliv.text
    assert c.post(f"/csf/deliverables/{deliv.json()['id']}/release", headers=h).is_success
    return svc


def test_csf_with_every_version_discarded_is_flagged_no_surfaced_version(
    app_client, tmp_path  # noqa: F811
) -> None:
    """Writer: `POST /csf/assessments/{id}/discard` (D-031). `_latest_assessment`
    then returns nothing, so no CSF version is read by the Playbook, and its
    headline zeros must say so."""
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()["id"]
    a = c.post(f"/csf/services/{svc}/assessments", headers=h).json()
    _csf_seed_and_tick(c, h, svc, ticked=1)
    assert c.post(f"/csf/assessments/{a['id']}/discard", headers=h).is_success

    report, table = _run_full(_url(tmp_path))
    assert report["surfaced_versions"]["csf"] == 0
    assert report["csf_tier_rows"]["all_versions"]["by_status"]["discarded"]["rows_read"] > 0
    assert "NO SURFACED VERSION (CSF)" in table
    assert "SURFACED VERSION HAS NO ROWS (CSF)" not in table


def test_a_surfaced_csf_version_with_no_rows_is_flagged(app_client, tmp_path) -> None:  # noqa: F811
    """v1 released with Playbook rows; v2 opened and never seeded. The Playbook
    reads v2, which holds no tier rows, so the headline zeros must say so."""
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc = _csf_v1_released(c, h)
    v2 = c.post(f"/csf/services/{svc}/assessments", headers=h).json()
    assert v2["status"] == "draft"

    report, table = _run_full(_url(tmp_path))
    assert report["surfaced_versions"]["csf"] == 1
    assert report["csf_tier_rows"]["surfaced"]["by_status"]["draft"]["rows_read"] == 0
    assert report["csf_tier_rows"]["all_versions"]["by_status"]["released"]["rows_read"] > 0
    assert "SURFACED VERSION HAS NO ROWS (CSF)" in table
    assert "NO SURFACED VERSION (CSF)" not in table


def _main_json(monkeypatch, capsys, url: str) -> tuple[int, dict, str]:
    """Run `main` IN PROCESS, so a monkeypatch reaches the engine calls."""
    monkeypatch.setenv("DATABASE_URL", url)
    code = m.main()
    out = capsys.readouterr().out
    table, payload = out.split(m.JSON_MARKER, 1)
    return code, json.loads(payload), table


def test_a_failure_in_the_without_freeze_pass_is_listed_not_dropped(
    app_client, tmp_path, monkeypatch, capsys  # noqa: F811
) -> None:
    """No stored input is known to make `analyze_gaps` raise there, so the
    failure is injected: only on the without-freeze LAUNCH map, the one map in
    this world holding a 2 (every stored stage is 4; the v2 draft holds none).
    The assessment must be LISTED, tagged with its pass, and not silently
    missing from the without-freeze line."""
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    _svc, a = _released_zt_on_four(c, h, bearer)
    real = m.analyze_gaps

    def raise_on_launch(fw, answers, **kw):
        if 2 in answers.values():
            raise ValueError("injected: the without-freeze launch pass")
        return real(fw, answers, **kw)

    monkeypatch.setattr(m, "analyze_gaps", raise_on_launch)
    code, report, _table = _main_json(monkeypatch, capsys, _url(tmp_path))
    assert code == 0
    bad = report["zt_assessments"]["not_evaluable"]
    assert [(b["assessment_id"], b["pass"]) for b in bad] == [(a["id"], "without_freeze")]
    assert "injected" in bad[0]["reason"]
    would = report["zt_released_without_freeze_assessments"]["all_versions"]["by_status"]
    assert would["released"]["assessments_evaluated"] == 0
    # The headline pass (stored stage) was unaffected.
    headline = report["zt_assessments"]["all_versions"]["by_status"]
    assert headline["released"]["assessments_evaluated"] == 1


def test_the_held_statuses_are_derived_from_the_rule(
    app_client, tmp_path, monkeypatch, capsys  # noqa: F811
) -> None:
    """`scope.zt_statuses_held_at_stored_stage` is derived from
    `zt_rule_applies`, so a change to the rule changes the scope line."""
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    _released_zt_on_four(c, h, bearer)
    _code, report, _table = _main_json(monkeypatch, capsys, _url(tmp_path))
    assert report["scope"]["zt_statuses_held_at_stored_stage"] == ["released"]
    monkeypatch.setattr(m, "zt_rule_applies", lambda status: status not in ("approved", "released"))
    _code, report, _table = _main_json(monkeypatch, capsys, _url(tmp_path))
    assert report["scope"]["zt_statuses_held_at_stored_stage"] == ["approved", "released"]


def test_the_flags_are_per_service_not_per_service_type(app_client, tmp_path) -> None:  # noqa: F811
    """CSF service A: one draft, seeded, read by the Playbook. CSF service B:
    v1 released with rows, v2 opened and never seeded, so the version its
    Playbook reads holds nothing. A's rows must not hide B's empty headline."""
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_a = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "A"}).json()["id"]
    c.post(f"/csf/services/{svc_a}/assessments", headers=h)
    _csf_seed_and_tick(c, h, svc_a, ticked=1)
    svc_b = _csf_v1_released(c, h)
    assert c.post(f"/csf/services/{svc_b}/assessments", headers=h).is_success

    report, table = _run_full(_url(tmp_path))
    by_service = {s["service_id"]: s for s in report["services"]["csf"]}
    assert by_service[svc_a]["rows_surfaced"] > 0
    assert by_service[svc_b]["rows_surfaced"] == 0
    assert by_service[svc_b]["rows_all_versions"] > 0
    flags = [line for line in table.splitlines() if "SURFACED VERSION HAS NO ROWS (CSF)" in line]
    assert len(flags) == 1, flags
    assert svc_b in flags[0]
    assert svc_a not in table.split("SURFACED VERSION HAS NO ROWS (CSF)", 1)[1].splitlines()[0]

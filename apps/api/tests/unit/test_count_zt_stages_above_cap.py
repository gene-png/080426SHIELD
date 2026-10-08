"""`scripts/count_zt_stages_above_cap.py` counts, reads only, and never prints a
zero it did not measure (#839, F1).

The world is built through the API, then the over-cap values are written
straight into the store, because no write path can produce them any more.
That is the state the script exists to find: rows stored before the guard.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from app.models.zt_assessment import ZtAnswer, ZtAssessment, ZtAssessmentStatus
from tests.unit.test_zt_run_ai import _admin_service, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

_API = Path(__file__).resolve().parents[2]
_SCRIPT = _API / "scripts" / "count_zt_stages_above_cap.py"


def _run(url: str | None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    if url is not None:
        env["DATABASE_URL"] = url
    return subprocess.run(  # noqa: S603 -- this interpreter, the repo's own script
        [sys.executable, str(_SCRIPT)], cwd=_API, env=env, capture_output=True, text=True
    )


def _db_path(url: str) -> Path:
    return Path(url.removeprefix("sqlite:///"))


def test_it_counts_each_field_per_status_and_writes_nothing(app_client) -> None:  # noqa: F811
    c, _ = app_client
    url = os.environ["DATABASE_URL"]
    h, svc_id, _ = _admin_service(c, "zero_trust_dod")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h).json()
    aid = uuid.UUID(a["id"])
    engine = create_engine(url, future=True)
    with Session(engine) as db:
        # 1.1 (no Advanced activity): current 3 and target 3 are both over.
        # 1.2 (has one): 3 is within its maximum. A retired row at 4 is over
        # the DoD ladder. A row at 2 is within every maximum.
        db.execute(
            update(ZtAnswer)
            .where(ZtAnswer.assessment_id == aid, ZtAnswer.capability_code == "DOD.USR.01")
            .values(maturity_stage=3, target_stage=3)
        )
        db.execute(
            update(ZtAnswer)
            .where(ZtAnswer.assessment_id == aid, ZtAnswer.capability_code == "DOD.USR.02")
            .values(maturity_stage=3)
        )
        db.execute(
            update(ZtAnswer)
            .where(ZtAnswer.assessment_id == aid, ZtAnswer.capability_code == "DOD.USR.03")
            .values(maturity_stage=2)
        )
        db.execute(
            update(ZtAssessment)
            .where(ZtAssessment.id == aid)
            .values(status=ZtAssessmentStatus.RELEASED)
        )
        db.commit()
    engine.dispose()

    before = _db_path(url).read_bytes()
    r = _run(url)
    assert r.returncode == 0, r.stderr
    # What was read, before what was found (review round 2, finding 5).
    assert "read: DoD assessments 1, DoD answer rows 45" in r.stdout, r.stdout
    assert "  released read: assessments 1, answer rows 45" in r.stdout, r.stdout
    assert "  draft read: assessments 0, answer rows 0" in r.stdout, r.stdout
    assert "NOTHING TO MEASURE" not in r.stdout, r.stdout
    assert "released: current stage over 1, target over 1" in r.stdout, r.stdout
    assert f"current {a['id']} DOD.USR.01 = 3" in r.stdout, r.stdout
    assert f"target {a['id']} DOD.USR.01 = 3" in r.stdout, r.stdout
    assert "DOD.USR.02" not in r.stdout and "DOD.USR.03" not in r.stdout, r.stdout
    assert "draft: current stage over 0, target over 0" in r.stdout, r.stdout
    assert _db_path(url).read_bytes() == before, "the script wrote to the database"


def test_a_clean_database_prints_zeros_and_exits_0(app_client) -> None:  # noqa: F811
    c, _ = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_dod")
    c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    r = _run(os.environ["DATABASE_URL"])
    assert r.returncode == 0, r.stderr
    # Clean because 45 rows were read, which the output says first.
    assert "read: DoD assessments 1, DoD answer rows 45" in r.stdout, r.stdout
    assert "NOTHING TO MEASURE" not in r.stdout, r.stdout
    for status in ("draft", "submitted", "approved", "released", "discarded"):
        assert f"{status}: current stage over 0, target over 0" in r.stdout, r.stdout


def test_a_database_with_no_dod_rows_says_it_read_none(app_client) -> None:  # noqa: F811
    """A readable database holding no DoD answers (here, only a CISA
    assessment) prints zeros that measured nothing. It must say so, so it can
    never read as the clean result above."""
    c, _ = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    r = _run(os.environ["DATABASE_URL"])
    assert r.returncode == 0, r.stderr
    assert "read: DoD assessments 0, DoD answer rows 0" in r.stdout, r.stdout
    assert (
        "NOTHING TO MEASURE: no DoD answer rows were read, so the zeros below "
        "are not a clean result"
    ) in r.stdout, r.stdout


def test_an_unreadable_database_exits_2_and_prints_no_count(tmp_path: Path) -> None:
    empty = tmp_path / "no-tables.db"
    empty.write_bytes(b"")
    r = _run(f"sqlite:///{empty}")
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "could not read the database" in r.stderr
    assert "over 0" not in r.stdout


def test_no_database_url_exits_2() -> None:
    r = _run(None)
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "DATABASE_URL is not set" in r.stderr

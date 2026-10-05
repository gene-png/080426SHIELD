"""#802 slice A: a what-if run does not hold the ATT&CK edit lock.

A what-if writes only its own tables, and its base is APPROVED or RELEASED,
which is locked already. So a what-if run in progress must not refuse edits to
the service's real draft, and must not be reported as the workspace's run in
progress (the coordinator's ruling (b), agreed by the advisor at 05:25Z). A
mitre_map run still does both: the exclusion is one named purpose, not a
loosened lock.
"""

from __future__ import annotations

import pytest

from app.ai.runs import NON_LOCKING_PURPOSES
from app.attack import scenario
from tests._ai_runs import defer_runs
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)
from tests.unit.test_attack_scenario_routes import (  # noqa: F401  (fixture)
    EDR,
    _world,
)

pytestmark = pytest.mark.unit


def _draft_row(w) -> str:
    """A new DRAFT version of the service, and one of its rows to edit."""
    r = w.c.post(f"/attack/services/{w.svc_id}/assessments", headers=w.h)
    assert r.status_code == 201, r.text
    return next(c["id"] for c in r.json()["coverage"] if c["technique_code"] == w.b)


def _patch(w, row_id: str):
    return w.c.patch(f"/attack/coverage/{row_id}", headers=w.h, json={"notes": "edited mid-run"})


def _running(w) -> dict | None:
    r = w.c.get(f"/ai-runs/services/{w.svc_id}", headers=w.h)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_what_if_purpose_is_the_one_excluded() -> None:
    assert frozenset({scenario.PURPOSE}) == NON_LOCKING_PURPOSES


def test_a_what_if_run_in_progress_neither_locks_the_draft_nor_shows_as_its_run(
    app_parts,  # noqa: F811
) -> None:
    w = _world(app_parts)
    w.answer({})
    runner = defer_runs(w.app)
    sid = w.create([EDR]).json()["id"]
    started = w.run(sid)
    assert started.status_code == 202, started.text
    # The what-if run IS in progress: its own read says so.
    assert w.get(sid)["run_status"] == "running"

    row_id = _draft_row(w)
    r = _patch(w, row_id)
    assert r.status_code == 200, r.text
    summary = _running(w)
    assert summary["running"] is None, summary
    assert summary["latest"] is None, summary
    assert runner.run_all() == 1


def test_a_mitre_map_run_in_progress_still_locks_the_draft_and_shows_as_its_run(
    app_parts,  # noqa: F811
) -> None:
    w = _world(app_parts)
    w.answer({})
    row_id = _draft_row(w)
    runner = defer_runs(w.app)
    started = w.c.post(
        f"/attack/services/{w.svc_id}/run-ai", headers=w.h, json={"serves": "offline"}
    )
    assert started.status_code == 202, started.text
    r = _patch(w, row_id)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "ai_run_in_progress"
    summary = _running(w)
    assert summary["running"]["id"] == started.json()["run_id"], summary
    assert runner.run_all() == 1

"""Measurement-only pytest plugin (not part of the repo).

Loaded with `-p ci_timing`. Records, per test and in total:
- setup / call / teardown durations (pytest's own report.duration);
- every alembic command.upgrade / command.downgrade: count, wall time, target,
  and which test phase it ran in;
- collection time.
Writes JSON to $CI_TIMING_OUT. Changes no behaviour: the wrappers call the
original functions with the original arguments and re-raise anything.
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict

import pytest

_T0 = time.perf_counter()
_state = {"phase": "collection", "nodeid": None}
_mig = defaultdict(lambda: {"count": 0, "seconds": 0.0})
_mig_by_phase = defaultdict(float)
_mig_per_test = defaultdict(float)
_mig_calls_per_test = defaultdict(int)
_phase = defaultdict(float)
_per_test = {}
_outcomes = defaultdict(int)
_collect = {}


def _wrap(name):
    from alembic import command

    orig = getattr(command, name)

    def timed(cfg, revision, *a, **k):
        t = time.perf_counter()
        try:
            return orig(cfg, revision, *a, **k)
        finally:
            dt = time.perf_counter() - t
            key = f"{name}:{revision}"
            _mig[key]["count"] += 1
            _mig[key]["seconds"] += dt
            _mig_by_phase[_state["phase"]] += dt
            if _state["nodeid"]:
                _mig_per_test[_state["nodeid"]] += dt
                _mig_calls_per_test[_state["nodeid"]] += 1

    setattr(command, name, timed)


def pytest_configure(config):
    _wrap("upgrade")
    _wrap("downgrade")


def pytest_collection_finish(session):
    _collect["seconds"] = time.perf_counter() - _T0
    _collect["items"] = len(session.items)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    _state.update(phase="setup", nodeid=item.nodeid)
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    _state.update(phase="call", nodeid=item.nodeid)
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):
    _state.update(phase="teardown", nodeid=item.nodeid)
    yield
    _state.update(phase="between", nodeid=None)


def pytest_runtest_logreport(report):
    _phase[report.when] += report.duration
    t = _per_test.setdefault(report.nodeid, {"setup": 0.0, "call": 0.0, "teardown": 0.0})
    t[report.when] = report.duration
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        _outcomes[report.outcome] += 1


def pytest_sessionfinish(session, exitstatus):
    wall = time.perf_counter() - _T0
    by_file = defaultdict(lambda: {"tests": 0, "seconds": 0.0, "migration_seconds": 0.0})
    for nodeid, t in _per_test.items():
        f = nodeid.split("::")[0]
        by_file[f]["tests"] += 1
        by_file[f]["seconds"] += sum(t.values())
        by_file[f]["migration_seconds"] += _mig_per_test.get(nodeid, 0.0)
    tests_with_migration = sum(1 for v in _mig_calls_per_test.values() if v)
    out = {
        "exitstatus": int(exitstatus),
        "wall_seconds": wall,
        "collection": _collect,
        "phase_seconds": dict(_phase),
        "outcomes": dict(_outcomes),
        "migration_total_seconds": sum(v["seconds"] for v in _mig.values()),
        "migration_by_phase": dict(_mig_by_phase),
        "migration_by_target": dict(_mig),
        "tests_that_ran_a_migration": tests_with_migration,
        "migration_calls_histogram": dict(
            sorted(
                defaultdict(int, {}).items()
            )
        ),
        "slowest_files": sorted(
            ({"file": k, **v} for k, v in by_file.items()), key=lambda r: -r["seconds"]
        )[:40],
        "slowest_tests": sorted(
            ({"test": k, "total": sum(v.values()), **v, "migration": _mig_per_test.get(k, 0.0)}
             for k, v in _per_test.items()),
            key=lambda r: -r["total"],
        )[:40],
    }
    hist = defaultdict(int)
    for v in _mig_calls_per_test.values():
        hist[v] += 1
    out["migration_calls_histogram"] = {str(k): v for k, v in sorted(hist.items())}
    with open(os.environ["CI_TIMING_OUT"], "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)

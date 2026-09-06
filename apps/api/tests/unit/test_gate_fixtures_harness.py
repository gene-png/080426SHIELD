"""The fixture harness must fail closed, and be able to fail at all.

This gate cannot fixture itself -- it is excluded from its own discovery, which
is the shape `CLAUDE.md` records for `check_recalled_counts`, whose help text is
a Python string its own pattern never reads. So its own both-states evidence
lives here instead, and every failure mode below was executed on the host before
being written down rather than reasoned about.

The exit-code split is the point. Exit 2 means "I could not look" -- a missing
root, a malformed case, an empty gate directory. Exit 1 means "I looked and
something is wrong" -- a gate returned the wrong code, or its cases do not meet
the contract. `check_audit_evidence`'s `is_code_change([])` printing
"documentation-only change, exempt" and exiting 0 is why those must never share
a branch.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from scripts.check_gate_fixtures import _EXTRA_GATES, DEFERRED, discover_gates, load_cases, main

# CI runs `pytest -m unit tests/unit`. WITHOUT this marker every test in this
# file is DESELECTED, and the suite reports the same "7111 passed" as `main`
# while running none of them -- which is exactly what the first CI run on this
# branch did: +12 deselected, +0 passed, and the aggregate looked clean because
# the pass count had not moved. A test suite going green over tests that never
# executed is the shape this whole PR is about, produced in the PR's own
# evidence. Module-level rather than 12 decorators so it cannot be forgotten on
# test 13.
pytestmark = pytest.mark.unit

_PASSING_PLAN = """### Total remaining: 12-18 sessions across the FOUR SIZED items

| Item | Estimate |
| --- | --- |
| 7 - a | 1.75-3 |
| 9 - b | 5.25-7.5 |
| 6 - c | 4-6 |
| 8 - d | 1-1.5 |
| **Total** | **12-18** |
"""


def _case(
    dir_: Path, *, expect: int, incident: str = "harness self-test", adversarial: bool = False
) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / "DELIVERY_PLAN.md").write_text(_PASSING_PLAN, encoding="utf-8")
    (dir_ / "case.json").write_text(
        json.dumps(
            {
                "incident": incident,
                "expect": expect,
                "adversarial": adversarial,
                "argv": ["{dir}/DELIVERY_PLAN.md"],
            }
        ),
        encoding="utf-8",
    )


def _root(tmp_path: Path) -> Path:
    """A fixture root positioned so the harness finds the real scripts dir."""
    root = tmp_path / "apps" / "api" / "tests" / "gates"
    root.mkdir(parents=True)
    real_scripts = Path(__file__).resolve().parents[2] / "scripts"
    link = tmp_path / "apps" / "api" / "scripts"
    link.mkdir(parents=True, exist_ok=True)
    # Copy EVERY gate the harness discovers, not just `check_*.py`. An earlier
    # version copied only the glob, so `leave_row_oracle.py` and
    # `mutation_sweep.py` were absent, DEFERRED named two gates that did not
    # exist in the fake tree, and `main` correctly returned 2 -- its stale-
    # exemption branch -- where these tests expect 1. The harness was right and
    # the helper was wrong, which is only visible now that these tests run at all.
    names = {p.name for p in real_scripts.glob("check_*.py")} | set(_EXTRA_GATES)
    for name in names:
        src = real_scripts / name
        if src.is_file():
            (link / name).write_bytes(src.read_bytes())
    return root


def test_missing_root_is_two_not_zero(tmp_path: Path) -> None:
    """The branch that matters: 'I could not look' must not read as a pass."""
    assert main(["x", str(tmp_path / "nope")]) == 2


def test_empty_gate_directory_is_two(tmp_path: Path) -> None:
    """A gate directory with no cases is nothing-to-check, which is not clean."""
    root = _root(tmp_path)
    (root / "check_plan_totals").mkdir()
    assert main(["x", str(root)]) == 2


def test_malformed_case_is_two_not_one(tmp_path: Path) -> None:
    root = _root(tmp_path)
    d = root / "check_plan_totals" / "broken"
    d.mkdir(parents=True)
    (d / "case.json").write_text("{ not json", encoding="utf-8")
    assert main(["x", str(root)]) == 2


def test_case_without_an_incident_is_rejected(tmp_path: Path) -> None:
    """An empty reason is not a reason -- the same rule test-integrity applies."""
    root = _root(tmp_path)
    d = root / "check_plan_totals" / "nameless"
    d.mkdir(parents=True)
    _case(d, expect=0, incident="   ")
    assert main(["x", str(root)]) == 2


# The four tests below assert the exit code AND the specific message.
#
# Asserting the code alone does not discriminate, and that was not a theory: a
# landed mutation disabling the negative-control requirement entirely
# (`if False:`) left every one of them GREEN. In a temp root every other gate is
# uncovered, so `main` returns 1 from "no fixtures and not in DEFERRED" no matter
# what the test broke -- each test passed on a cause it was not testing. That is
# the surviving-mutant shape this PR exists to catch, produced inside the PR's
# own evidence, and found only by proving the mutation had landed before reading
# the result.


def test_no_negative_control_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Fixtures that only ever pass prove the gate RUNS, not that it discriminates.

    This is the whole reason the harness exists, so it is the assertion that must
    not be allowed to rot.
    """
    root = _root(tmp_path)
    _case(root / "check_plan_totals" / "only-passing", expect=0, adversarial=True)
    assert main(["x", str(root)]) == 1
    assert "NO NEGATIVE CONTROL" in capsys.readouterr().out


def test_no_adversarial_case_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _root(tmp_path)
    _case(root / "check_plan_totals" / "passing", expect=0)
    _case(root / "check_plan_totals" / "failing", expect=2)
    assert main(["x", str(root)]) == 1
    assert "no case marked adversarial" in capsys.readouterr().out


def test_wrong_exit_code_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _root(tmp_path)
    _case(root / "check_plan_totals" / "passing", expect=0)
    _case(root / "check_plan_totals" / "mislabelled", expect=1, adversarial=True)
    assert main(["x", str(root)]) == 1
    out = capsys.readouterr().out
    assert "expected exit 1, got 0" in out
    assert "mislabelled" in out


def test_uncovered_gate_is_not_silently_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Silence must not be how coverage shrinks.

    A gate with neither fixtures nor a DEFERRED reason fails, so adding a gate
    cannot quietly reduce what this harness examines.
    """
    root = _root(tmp_path)
    _case(root / "check_plan_totals" / "passing", expect=0)
    _case(root / "check_plan_totals" / "failing", expect=2, adversarial=True)
    assert main(["x", str(root)]) == 1
    assert "no fixtures and not in DEFERRED" in capsys.readouterr().out


def test_deferred_entries_all_name_a_real_gate(tmp_path: Path) -> None:
    """A DEFERRED key that no longer exists is a stale exemption.

    Same class as an agent definition citing a merged branch: the exemption
    outlives the thing it excused, and nothing notices.
    """
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    assert set(DEFERRED) <= set(discover_gates(scripts))


def test_deferred_reasons_are_not_empty() -> None:
    for gate, reason in DEFERRED.items():
        assert reason.strip(), f"{gate} is deferred with no reason"


def test_universe_equals_the_other_gate_enumeration() -> None:
    """Two enumerations of this repo's gates must not drift apart.

    `test_gate_crash_exit_code.GATES` pins the crash-exits-2 convention; this
    harness pins can-it-fail-at-all. Nothing connected them, and they were
    already unequal: this harness globbed `check_*.py` and therefore could not
    see `leave_row_oracle.py`, a real CI gate (ci.yml:96) whose name does not
    match -- a discovery predicate blind to a live gate, inside the tool written
    to catch predicates blind to live cases.

    Asserting equality is cheaper than either list noticing the other has grown.
    """
    # Loaded by PATH, not by name: `tests/unit` is not guaranteed on sys.path,
    # and a bare import made this test fail with ModuleNotFoundError -- which
    # would have read as "the enumerations diverged" rather than "the import
    # broke". A test whose failure names the wrong cause is its own defect.
    spec = importlib.util.spec_from_file_location(
        "_gate_crash_exit_code", Path(__file__).with_name("test_gate_crash_exit_code.py")
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    GATES = module.GATES

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    mine = set(discover_gates(scripts))
    theirs = {f"{stem}.py" for stem, _ in GATES}
    assert mine == theirs, (
        f"gate enumerations diverged -- only here: {sorted(mine - theirs)}; "
        f"only in GATES: {sorted(theirs - mine)}"
    )


def test_load_cases_reports_problems_rather_than_skipping(tmp_path: Path) -> None:
    """A case it cannot parse must surface, never be dropped from the count."""
    d = tmp_path / "gate" / "no-spec"
    d.mkdir(parents=True)
    cases, problems = load_cases(tmp_path / "gate")
    assert cases == []
    assert problems and "no case.json" in problems[0]

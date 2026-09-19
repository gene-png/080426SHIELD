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
from scripts.check_gate_fixtures import (
    _GATE_MARKER,
    DEFERRED,
    discover_gates,
    discover_shell_gates,
    load_cases,
    main,
    unwired_gates,
)

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
    # Copy every gate by the SAME predicate the harness discovers with -- the
    # crash-is-not-a-verdict marker -- rather than by a glob. An earlier version
    # copied only `check_*.py`, so `leave_row_oracle.py` and `mutation_sweep.py`
    # were absent, DEFERRED named two gates missing from the fake tree, and `main`
    # correctly returned 2 from its stale-exemption branch where these tests
    # expect 1. The harness was right and the helper was wrong, which was only
    # visible once these tests ran at all. Deriving the copy set from the same
    # property keeps the helper from drifting away from the thing it stands in for.
    for src in real_scripts.glob("*.py"):
        try:
            text = src.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _GATE_MARKER in text or src.name.startswith("check_"):
            (link / src.name).write_bytes(src.read_bytes())
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

    The universe is BOTH languages since #318, and the two halves are asserted
    SEPARATELY because only one of them is always reachable. The api container
    mounts `apps/api` at `/app`, so the repo root — and with it
    `tests/gates/*.sh` — does not exist inside it (#314). Checking the union
    would make this test fail in the container and pass in CI; checking only
    the Python half would let the shell entries read as stale, and the cheapest
    route to green is deleting them, which is how the exemption that hid two
    unwired gates comes back.

    So: the Python half always runs, and the shell half SKIPS WITH A REASON
    when the directory is out of reach. A skip is visible in the output; a
    silently-empty universe is not.
    """
    api = Path(__file__).resolve().parents[2]
    python_gates = set(discover_gates(api / "scripts"))
    shell_entries = {k for k in DEFERRED if k.endswith(".sh")}
    assert set(DEFERRED) - shell_entries <= python_gates

    repo = api.parents[1] if len(api.parents) >= 2 else None
    shell_dir = (repo / "tests" / "gates") if repo is not None else None
    if shell_dir is None or not shell_dir.is_dir():
        pytest.skip(
            f"repo-root tests/gates is not reachable from {api} — the api "
            f"container mounts apps/api at /app (#314), so the shell half of "
            f"the DEFERRED universe cannot be checked here. It is checked on "
            f"a full checkout, which is what CI runs."
        )
    assert shell_entries <= set(discover_shell_gates(shell_dir))


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


# ---------------------------------------------------------------------------
# #318 -- a gate that runs NOWHERE cannot fail, and nothing said so.
#
# `web_install_guard.sh` and `prettier_hook.sh` each shipped with real
# both-states assertions inside and no workflow, no CI step and no script
# invoking either. Fixture coverage cannot detect that: a gate can be perfectly
# fixtured and still never run. And the harness could not have reported them
# anyway, because it discovered gates by globbing `apps/api/scripts/*.py` -- so
# a SHELL gate at the REPO ROOT escaped the registry in silence.
# ---------------------------------------------------------------------------


def _workflows(tmp_path: Path, body: str) -> Path:
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(body, encoding="utf-8")
    return wf


def test_a_gate_no_workflow_invokes_is_reported(tmp_path: Path) -> None:
    wf = _workflows(tmp_path, "jobs:\n  x:\n    steps:\n      - run: python a.py\n")
    assert unwired_gates(["check_a.py", "orphan.sh"], wf) == ["check_a.py", "orphan.sh"]


def test_a_gate_invoked_by_its_stem_counts_as_wired(tmp_path: Path) -> None:
    """Four of the nine Python gates are never named by their `.py` filename.

    `check_audit_evidence` arrives as `from scripts.check_audit_evidence import
    ...` inside a `python -c`, and `check_test_integrity` as `-m
    scripts.check_test_integrity`. Matching filenames reports four live gates
    unwired, which would make the check's first run a wall of false positives
    and its second run a deleted check.
    """
    wf = _workflows(
        tmp_path,
        "jobs:\n  x:\n    steps:\n"
        '      - run: python -c "from scripts.check_audit_evidence import missing_evidence"\n'
        "      - run: python -m scripts.check_test_integrity tests\n",
    )
    assert unwired_gates(["check_audit_evidence.py", "check_test_integrity.py"], wf) == []


def test_a_gate_named_only_in_a_comment_is_unwired(tmp_path: Path) -> None:
    """THE ADVERSARIAL CASE, and the reason comments are stripped at all.

    `audit-gate.yml` mentions `leave_row_oracle` in a comment ABOUT a gate that
    job does not run. Matching raw workflow text would read that mention as an
    invocation — a gate counted as running because somebody wrote its name in
    prose, which is precisely the substitution this harness exists to refuse.

    The assertion is worth more than the stripping: without it, someone
    simplifying `unwired_gates` back to a raw `in text` finds every other test
    in this file still green.
    """
    wf = _workflows(
        tmp_path,
        "jobs:\n  x:\n    steps:\n"
        "      # check_ghost is the gate this job does NOT run; see #318\n"
        "      - run: python apps/api/scripts/check_real.py\n",
    )
    assert unwired_gates(["check_ghost.py", "check_real.py"], wf) == ["check_ghost.py"]


def test_shell_gates_are_discovered_at_the_repo_root(tmp_path: Path) -> None:
    """Derived from LOCATION, not from a property in the file.

    Weaker than `discover_gates`, which reads the crash-is-not-a-verdict handler
    out of each script, and weaker on purpose: bash has no equivalent of that
    handler. Pinned here so the weaker derivation is at least the one that runs.
    """
    gates = tmp_path / "tests" / "gates"
    gates.mkdir(parents=True)
    (gates / "b_guard.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (gates / "a_guard.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (gates / "notes.md").write_text("not a gate\n", encoding="utf-8")
    (gates / "subdir").mkdir()
    assert discover_shell_gates(gates) == ["a_guard.sh", "b_guard.sh"]


def test_a_missing_shell_gate_directory_is_not_an_empty_list(tmp_path: Path) -> None:
    """`discover_shell_gates` returns [] for a missing directory, so the CALLER
    must be the one that fails closed — and `main` does, with exit 2.

    Asserted as a pair rather than trusting the helper: an empty list and "the
    directory is not there" are the same value, which is the shape D-051 is
    about. The helper is allowed to conflate them only because nothing reads it
    without checking `is_dir()` first.
    """
    assert discover_shell_gates(tmp_path / "nope") == []
    assert not (tmp_path / "nope").is_dir()


def test_the_explicit_root_skip_is_printed_not_silent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Running against a synthetic fixture root cannot check the real repo, and
    the harness says so out loud.

    An unannounced skip would make every tmp_path test in this file look like
    evidence that the wiring check passed. "I did not look" and "I looked and it
    was fine" must not be the same output — this file's own organising rule,
    turned on the file itself.
    """
    root = _root(tmp_path)
    _case(root / "check_plan_totals" / "ok", expect=0)
    _case(root / "check_plan_totals" / "bad", expect=1)
    _case(root / "check_plan_totals" / "cantlook", expect=2)
    main(["x", str(root)])
    out = capsys.readouterr().out
    assert "NOT CHECKED under an explicit fixture root" in out
    assert "shell-gate discovery and the gate-wiring check" in out

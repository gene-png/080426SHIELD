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
    NON_GATE_SCRIPTS,
    compose_sources,
    discover_gates,
    discover_shell_gates,
    invocation_text,
    load_cases,
    main,
    undiscovered_gates,
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
    dir_: Path,
    *,
    expect: int,
    incident: str = "harness self-test",
    adversarial: bool = False,
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


def test_no_negative_control_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fixtures that only ever pass prove the gate RUNS, not that it discriminates.

    This is the whole reason the harness exists, so it is the assertion that must
    not be allowed to rot.
    """
    root = _root(tmp_path)
    _case(root / "check_plan_totals" / "only-passing", expect=0, adversarial=True)
    assert main(["x", str(root)]) == 1
    assert "NO NEGATIVE CONTROL" in capsys.readouterr().out


def test_no_adversarial_case_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _root(tmp_path)
    _case(root / "check_plan_totals" / "passing", expect=0)
    _case(root / "check_plan_totals" / "failing", expect=2)
    assert main(["x", str(root)]) == 1
    assert "no case marked adversarial" in capsys.readouterr().out


def test_wrong_exit_code_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
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
        "_gate_crash_exit_code",
        Path(__file__).with_name("test_gate_crash_exit_code.py"),
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
    assert (
        unwired_gates(["check_audit_evidence.py", "check_test_integrity.py"], wf) == []
    )


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
    # Named `*.sh` on purpose. As `subdir` it never matched the glob, so
    # deleting `if p.is_file()` from `discover_shell_gates` left this test
    # green -- one deletable clause, nothing noticing, in the PR about tests
    # that cannot fail.
    (gates / "subdir.sh").mkdir()
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


def _repo_shaped(tmp_path: Path, *, workflow: str, shell_gates: list[str]) -> Path:
    """A tmp tree `repo_root_for` can actually find, so `main` takes the real
    branch instead of the skip.

    This helper is the point of the rewrite. Every `main([...])` test passes an
    explicit fixture root, and the wiring check used to be skipped on exactly
    that condition — so the verdict this whole change exists to produce was
    reachable from no test at all, while three tests called `unwired_gates`
    directly and looked like coverage.
    """
    root = _root(tmp_path)
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(workflow, encoding="utf-8")
    gates = tmp_path / "tests" / "gates"
    gates.mkdir(parents=True)
    for name in shell_gates:
        (gates / name).write_text(
            "#!/bin/sh" + chr(10) + "exit 0" + chr(10), encoding="utf-8"
        )
    _case(root / "check_plan_totals" / "ok", expect=0)
    _case(root / "check_plan_totals" / "bad", expect=1)
    _case(root / "check_plan_totals" / "cantlook", expect=2)
    _case(root / "check_plan_totals" / "adv", expect=1, adversarial=True)
    return root


def test_main_fails_when_a_gate_no_workflow_invokes_exists(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Red-on-revert for the verdict, through `main` rather than the helper.

    Delete the four lines in `main` that turn `unwired` into a verdict and this
    goes red. Before it existed, that deletion left the whole suite green and CI
    green, because on the real tree no gate is unwired — the headline feature
    would have become a computed-and-discarded list with nothing to notice.
    """
    workflow = chr(10).join(
        ["jobs:", "  x:", "    steps:", "      - run: python check_plan_totals.py", ""]
    )
    root = _repo_shaped(tmp_path, workflow=workflow, shell_gates=["orphan_guard.sh"])
    assert main(["x", str(root)]) == 1
    out = capsys.readouterr().out
    assert "gates no workflow invokes" in out
    assert "orphan_guard.sh" in out


def test_main_refuses_when_the_shell_gate_directory_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2, not 1 and not 0: the repo was found and one half of it was not.

    Distinct from `repo is None`, which is the container case and is printed
    rather than returned. Two different "I could not look"s, and only this one
    is a real absence on a tree that otherwise looks complete.
    """
    root = _repo_shaped(tmp_path, workflow="jobs: {}" + chr(10), shell_gates=[])
    (tmp_path / "tests" / "gates").rmdir()
    (tmp_path / "tests").rmdir()
    assert main(["x", str(root)]) == 2
    assert "no shell-gate directory at" in capsys.readouterr().out


def test_main_skips_the_repo_half_out_loud_when_there_is_no_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The container case (#314), and the skip must be AUDIBLE.

    `apps/api` is mounted at `/app`, so there is no `.github/` above the fixture
    root and the repo-derived half has nothing to read. The fixture checks are
    still worth running, so this prints and continues rather than returning —
    which is only defensible because it says so.
    """
    root = _root(tmp_path)
    _case(root / "check_plan_totals" / "ok", expect=0)
    _case(root / "check_plan_totals" / "bad", expect=1)
    _case(root / "check_plan_totals" / "cantlook", expect=2)
    _case(root / "check_plan_totals" / "adv", expect=1, adversarial=True)
    main(["x", str(root)])
    out = capsys.readouterr().out
    assert "NOT CHECKED" in out
    assert "no `.github/workflows` above" in out
    # And it CONTINUED: the fixture half ran, evidenced by its own output
    # naming a gate. The exit code is deliberately not asserted -- these tmp
    # fixtures do not satisfy the contract (`_case` writes no
    # `stdout_contains`, which every expect-2 case needs), so pinning the code
    # would pin an incidental contract failure rather than the skip behaviour
    # this test is named for.
    assert "check_plan_totals" in out, (
        "the run stopped at the skip instead of continuing to the fixture "
        "checks, which is the whole reason the skip prints rather than returns"
    )


def test_a_stem_contained_in_another_stem_is_not_counted_as_wired(
    tmp_path: Path,
) -> None:
    """The over-match direction, which is the SILENT one.

    `check_plan` is a substring of `check_plan_totals`, which CI runs. A bare
    `stem not in text` test reported `check_plan.py` wired while nothing
    invoked it — #318 reintroduced one naming collision later, and discoverable
    only by a human reading PRs, which is how #318 was found the first time.

    The false-positive direction the matcher trades against is loud: a wall of
    red on live gates, investigated inside one run. This one is silent, so it
    is the one that gets a test.
    """
    wf = _workflows(
        tmp_path,
        "jobs:\n  x:\n    steps:\n      - run: python check_plan_totals.py FILE\n",
    )
    assert unwired_gates(["check_plan.py"], wf) == ["check_plan.py"]
    assert unwired_gates(["check_plan_totals.py"], wf) == []


def test_a_module_path_invocation_still_counts_as_wired(tmp_path: Path) -> None:
    r"""The boundary must not reject a dotted module path.

    `scripts.check_audit_evidence` puts a `.` immediately before the stem. A
    lookbehind excluding `[\w.]` — the obvious spelling, and the one first
    tried here — rejects it, and the gate then reports four live gates unwired.
    The lookbehind excludes word characters only, and this is what holds that
    distinction in place.
    """
    wf = _workflows(
        tmp_path,
        "jobs:\n  x:\n    steps:\n"
        '      - run: python -c "from scripts.check_audit_evidence import missing_evidence"\n',
    )
    assert unwired_gates(["check_audit_evidence.py"], wf) == []


# ---------------------------------------------------------------------------
# THE UNDISCOVERED GATE (#296, #327) -- a gate in NEITHER registry.
#
# `test_universe_equals_the_other_gate_enumeration` cross-checks
# `discover_gates` against `test_gate_crash_exit_code.GATES`. That catches
# DRIFT BETWEEN the two and is structurally blind to a script missing from
# BOTH: two lists agreeing about a file neither contains is the answer they
# were always going to give. #296's two gates were exactly that, and the
# registry check passed BECAUSE the thing it should have found was not in the
# registry.
#
# `undiscovered_gates` is a THIRD oracle whose population comes from outside
# both lists -- the files that decide what CI executes. The first test below
# is that specific case; the rest are the boundaries that stop it becoming a
# wall of false positives, which is how a check gets deleted.
# ---------------------------------------------------------------------------


def _scripts(tmp_path: Path, files: dict[str, str]) -> Path:
    scripts = tmp_path / "apps" / "api" / "scripts"
    scripts.mkdir(parents=True)
    for name, body in files.items():
        (scripts / name).write_text(body, encoding="utf-8")
    return scripts


#: A body carrying the handler, i.e. a gate the marker-based discovery can see.
#: Built FROM `_GATE_MARKER` rather than spelled out, because what is under
#: test is whether discovery keys on that constant -- spelling it out would
#: leave these asserting a dead literal the day the constant moves.
_MARKED = f"# {_GATE_MARKER}\n"
_UNMARKED = "# an ordinary script\n"


def test_a_workflow_invoked_script_with_no_marker_is_reported(tmp_path: Path) -> None:
    """THE CASE #296 WAS, and the one no other check in this file can see.

    A script CI runs, carrying no handler, in no hand list. `discover_gates`
    cannot see it -- the marker is absent. `test_gate_crash_exit_code.GATES`
    does not list it. So the two enumerations agree perfectly, about nothing,
    and both report clean.

    The precondition is asserted rather than assumed: without it, a change
    making the marker match everything would leave this test green while the
    case it is named for had stopped being reachable.
    """
    scripts = _scripts(
        tmp_path, {"check_ghost.py": _UNMARKED, "check_real.py": _MARKED}
    )
    wf = _workflows(
        tmp_path,
        "jobs:\n  x:\n    steps:\n"
        "      - run: python apps/api/scripts/check_ghost.py\n"
        "      - run: python apps/api/scripts/check_real.py\n",
    )

    assert "check_ghost.py" not in discover_gates(scripts), (
        "precondition: the marker-based registry must be blind to it, or this "
        "test is not exercising the undiscovered case at all"
    )
    assert undiscovered_gates(scripts, wf) == ["check_ghost.py"]


def test_a_marked_gate_is_never_reported_as_undiscovered(tmp_path: Path) -> None:
    """THE PASSING STATE. Without it the report above could be unconditional."""
    scripts = _scripts(tmp_path, {"check_real.py": _MARKED})
    wf = _workflows(
        tmp_path, "jobs:\n  x:\n    steps:\n      - run: python check_real.py\n"
    )
    assert undiscovered_gates(scripts, wf) == []


def test_a_script_no_workflow_invokes_is_not_reported(tmp_path: Path) -> None:
    """The population is what CI RUNS, not every file in the directory.

    `apps/api/scripts` holds loaders and extractors nothing in CI invokes.
    Reporting those makes the first run a wall of false positives, and a check
    whose first run is noise is a check somebody deletes -- the failure mode
    `unwired_gates` records for filename-versus-stem matching.
    """
    scripts = _scripts(tmp_path, {"load_things.py": _UNMARKED})
    wf = _workflows(tmp_path, "jobs:\n  x:\n    steps:\n      - run: echo hi\n")
    assert undiscovered_gates(scripts, wf) == []


def test_a_declared_non_gate_is_not_reported(tmp_path: Path) -> None:
    """The exemption is BY NAME and carries a reason -- the `DEFERRED` shape.

    Driven through the real `NON_GATE_SCRIPTS` rather than a patched copy, so
    emptying it makes this red instead of leaving it asserting a stub.
    """
    name = next(iter(NON_GATE_SCRIPTS))
    scripts = _scripts(tmp_path, {name: _UNMARKED})
    wf = _workflows(tmp_path, f"jobs:\n  x:\n    steps:\n      - run: python {name}\n")
    assert undiscovered_gates(scripts, wf) == []


def test_every_declared_non_gate_states_a_reason() -> None:
    """An empty reason is not a reason.

    `load_cases` enforces exactly this for fixture incidents; an exemption list
    whose entries may be blank is how coverage shrinks in silence.
    """
    empty = [k for k, v in NON_GATE_SCRIPTS.items() if not str(v).strip()]
    assert empty == [], f"declared non-gates with no stated reason: {empty}"


def test_a_private_helper_is_not_a_candidate(tmp_path: Path) -> None:
    """`_common.py` is imported by gates, so its stem appears in workflow text
    whenever one of them is invoked as a module. Treating it as a candidate
    reports a finding with no available remedy."""
    scripts = _scripts(tmp_path, {"_common.py": _UNMARKED})
    wf = _workflows(
        tmp_path, "jobs:\n  x:\n    steps:\n      - run: python _common.py\n"
    )
    assert undiscovered_gates(scripts, wf) == []


def test_the_compose_file_is_an_invocation_source(tmp_path: Path) -> None:
    """A gate invoked ONLY by `docker-compose.yml` is wired, and reading just
    `.github/workflows` said otherwise.

    Not hypothetical: `check_mount_matches_database.py` is invoked there, one
    line before `alembic upgrade head`, exactly where its own docstring says it
    belongs -- and the e2e and demo jobs both `docker compose up`. It was
    reported unwired the moment #338's marker put it in the registry, and the
    tempting repair was to add a workflow step. That would have been a
    certificate over the wrong proposition: CI starts from fresh volumes, so
    the stale-mount state that gate detects cannot arise there, and the step
    could only ever pass.

    BOTH directions asserted, because `extra` defaults to empty -- so the
    without-compose case is the state every other caller in this file is in,
    and a change quietly reading the compose file by default would leave the
    positive half green and mean something different.
    """
    wf = _workflows(tmp_path, "jobs:\n  x:\n    steps:\n      - run: echo hi\n")
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  api:\n    command: python scripts/check_mount.py && alembic upgrade head\n",
        encoding="utf-8",
    )

    assert unwired_gates(["check_mount.py"], wf) == ["check_mount.py"]
    assert unwired_gates(["check_mount.py"], wf, compose_sources(tmp_path)) == []


def test_compose_sources_are_globbed_not_named(tmp_path: Path) -> None:
    """An override file counts without anyone editing this checker.

    A hand list of one entry is an enumeration, and what enumerations miss is
    this whole file's subject. The unrelated `.yml` is the negative half: the
    glob must not widen to every file at the repo root.
    """
    (tmp_path / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "docker-compose.ci.yaml").write_text("services: {}\n", encoding="utf-8")
    (tmp_path / "unrelated.yml").write_text("services: {}\n", encoding="utf-8")
    assert [p.name for p in compose_sources(tmp_path)] == [
        "docker-compose.ci.yaml",
        "docker-compose.yml",
    ]


def test_a_missing_extra_source_is_skipped_not_a_crash(tmp_path: Path) -> None:
    """A repo with no compose file is legitimate, so a named-but-absent source
    is skipped -- and the workflows half still has to be read, which is what
    this asserts. Returning early on the missing file would turn "no compose
    file" into "nothing is invoked", the could-not-look/nothing-wrong merge
    this harness exists to refuse."""
    wf = _workflows(
        tmp_path, "jobs:\n  x:\n    steps:\n      - run: python check_real.py\n"
    )
    assert "check_real.py" in invocation_text(wf, [tmp_path / "docker-compose.yml"])

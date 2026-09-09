#!/usr/bin/env python
"""Prove every gate CAN FAIL -- not merely that it runs and prints something.

WHY THIS EXISTS. This repo keeps producing checks whose inputs cannot
distinguish their pass state from their fail state (#213). The check runs, goes
green, and the green means nothing, because no input it actually saw could have
made it red. Recorded instances: a predicate enumerating HEAD/index/tracked
files that therefore excluded `git stash drop`, the operation that prompted it;
a duplicate-D-number regex collapsing `D-059a` into `D-059`; a dashboard suite
in which every fixture seeded a state where the two candidate fields coincided;
`git stash show --stat` accepted as proof of archive recovery when it cannot
display a `-u` stash's untracked parent at all.

`CLAUDE.md` already carries the half-rule -- "a guard must be observed in BOTH
states before it is trusted" -- and it has been losing, because it is a habit
that fires only when someone remembers to ask. This makes it mechanical.

## The contract

Every gate under `apps/api/scripts/` is either covered by fixtures here or named
in DEFERRED with a reason. A covered gate must have:

  * at least one case the gate PASSES (exit 0);
  * at least one case the gate FAILS with exit 1 -- the NEGATIVE CONTROL, without
    which the suite proves the gate runs and not that it discriminates. A 2 does
    not satisfy it: 1 and 2 are the codes D-051 exists to keep apart;
  * at least one case expecting exit 2, so the fail-closed half is covered too,
    and it carries `stdout_contains` -- a gate has several "could not look"
    branches and the code alone cannot say which one fired;
  * at least one case marked `adversarial`: input a reasonable person would
    expect to pass, that must not. Ordinary cases test the rule; adversarial
    cases test the boundary, and the boundary is where all of these have broken.

Every case names the INCIDENT it derives from, because a fixture derived from the
rule rather than from the failure is the inversion that produced the defects
above.

**What is mechanised is that the claim EXISTS; that it is TRUE is not, and
cannot be.** This file rejects a missing or whitespace-only `incident`. It cannot
tell whether the incident happened, whether the figures in it are real, or
whether it describes this fixture. Four incident fields in this corpus were found
inaccurate by an adversarial pass and corrected in `0ab309c` -- one claimed two
documents agreed on a figure where they give 11.5-17.5 and 12-18, one cited a
count that conflates three different populations, one described a two-line marker
as spanning three. Every one passed this gate.

That is the same scoping as the tier-1 claim below: form is mechanisable,
implication is not. Read "traceable incident" as a convention this file makes
visible, not a guarantee it enforces -- the enforcement is a reader.

## Fail-closed, per D-051

Exit 2 is "I could not look": fixture root missing, no gates discovered, a gate
directory with no cases, a malformed `case.json`, DEFERRED naming a gate that
does not exist. Exit 1 is "I looked and something is wrong": a gate returned the
wrong code, or its cases do not meet the contract above. Those must never share
a branch -- `check_audit_evidence`'s `is_code_change([])` printing
"documentation-only change, exempt" and exiting 0 is the recorded reason.

## What it does NOT do

It proves a gate CAN fail. It does not prove a gate asks the right question, and
nothing mechanical will -- see #213: form is mechanisable, implication is not.

**This gate cannot see itself.** It is excluded from its own discovery and is
covered by unit tests instead. That is the same shape `CLAUDE.md` records for
`check_recalled_counts`, whose help text is a Python string its own pattern
never reads. Stated here rather than left to be discovered later.

Usage:  python apps/api/scripts/check_gate_fixtures.py [FIXTURE_ROOT]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Gates knowingly without fixtures, each with its reason. A gate in neither this
# mapping nor the fixture tree FAILS the run: silence must not be how coverage
# quietly shrinks.
DEFERRED: dict[str, str] = {
    "leave_row_oracle.py": (
        "STRUCTURALLY unfixturable, which is a stronger reason than the one first "
        "recorded here. --check-registry takes no path: REPO_APP and TESTS are "
        "derived from __file__, and discover_tables() imports the matrix modules by "
        "name after a sys.path.insert. argv carries only the flag. There is no "
        "invocation that points this gate at a fixture directory, so covering it "
        "means changing the script rather than adding a case. The reason previously "
        "written here -- 'a stand-in redact.py plus stand-in truth tables' -- was "
        "shared with check_separator_classes, whose deferral did NOT survive review "
        "and is now fixtured; anyone rejecting that argument would have read this "
        "entry as the same rejected one and spent a session rediscovering the real "
        "blocker"
    ),
    "mutation_sweep.py": (
        "not a gate CI can fail on: mutation-sweep.yml carries continue-on-error on "
        "the job, with the comment 'A survivor is a question to answer, not a build "
        "failure. This job reports; it never blocks anything.' That is the binding "
        "fact. Two weaker ones were recorded here first and one was wrong -- it is "
        "schedule AND workflow_dispatch, not schedule-only, and the tee pipe is the "
        "least of the three. Carried in this universe because it follows the same "
        "0/1/2 convention and a developer running it by hand reads exit 1 as "
        "'surviving mutants'"
    ),
}

_SELF = "check_gate_fixtures.py"
_REQUIRED_KEYS = ("incident", "expect", "argv")

# What MAKES a script a gate in this repo: the crash-is-not-a-verdict handler.
# Every gate ends with it, no non-gate has it, and `test_gate_crash_exit_code`
# already uses this exact string as its own marker.
_GATE_MARKER = "crash != verdict"


def scripts_dir_for(root: Path) -> Path:
    """The scripts directory beside a fixture root at <api>/tests/gates."""
    return root.parents[1] / "scripts"


def discover_gates(scripts: Path) -> list[str]:
    """Every gate, DERIVED from the convention that makes a script a gate.

    A gate here is a script that returns 0/1/2 verdicts and therefore carries the
    crash-is-not-a-verdict handler. That property is IN THE FILE, so this notices
    a gate nobody told it about.

    Two enumerations preceded this and both were wrong. The first globbed
    `check_*.py` and could not see `leave_row_oracle.py`, a real CI gate whose
    name does not match -- the trap `CLAUDE.md` names explicitly. The repair was a
    two-name hand list pinned to a SECOND hand list in
    `test_gate_crash_exit_code.GATES`: two enumerations that catch drift between
    themselves while neither can notice the world grew. That is the same hole one
    level up, and `CLAUDE.md` is explicit -- prefer a derivation over a
    synchronisation.

    Rejected alternative, recorded because it looks right: deriving from the
    scripts the WORKFLOWS invoke. Measured, that returns 11 -- it picks up
    `seed_demo.py` and `fire_scheduled_triggers.py`, which CI runs and which are
    not gates. It answers "what does CI execute", not "what is a gate".

    Residual, stated rather than papered over: a gate written WITHOUT the handler
    is invisible here. That is a convention violation in its own right, and
    `test_gate_crash_exit_code` exists to catch it -- but only for gates already
    in its list, so a gate with neither the marker nor an entry is missed by both.
    Narrower than a hand list, not zero.
    """
    found: set[str] = set()
    for path in sorted(scripts.glob("*.py")):
        if path.name == _SELF:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _GATE_MARKER in text:
            found.add(path.name)
    return sorted(found)


def load_cases(gate_dir: Path) -> tuple[list[dict], list[str]]:
    """Return (cases, problems).

    A malformed case is a PROBLEM, never a silent skip -- a fixture the harness
    cannot read is the harness not looking, which is exit 2 and not exit 0.
    """
    cases: list[dict] = []
    problems: list[str] = []
    for case_dir in sorted(p for p in gate_dir.iterdir() if p.is_dir()):
        spec = case_dir / "case.json"
        if not spec.is_file():
            problems.append(f"{case_dir.name}: no case.json")
            continue
        try:
            data = json.loads(spec.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{case_dir.name}: unreadable case.json ({type(exc).__name__})")
            continue
        missing = [k for k in _REQUIRED_KEYS if k not in data]
        if missing:
            problems.append(f"{case_dir.name}: case.json missing {', '.join(missing)}")
            continue
        if not str(data["incident"]).strip():
            problems.append(f"{case_dir.name}: empty incident is not a reason")
            continue
        data["_dir"] = case_dir
        cases.append(data)
    return cases, problems


def run_case(scripts: Path, gate: str, case: dict) -> tuple[int, str]:
    """Return (exit code, combined output).

    The output is RETURNED rather than discarded because an exit code alone does
    not discriminate. `check_plan_totals` has four distinct exit-2 branches; two
    fixtures assert 2, and until `stdout_contains` existed either could have
    started returning 2 from a different branch and still passed -- two copies of
    one test wearing different names. This PR fixed exactly that defect in its own
    unit tests, by adding message assertions after a landed mutation left all
    twelve green, and did not carry the fix to the fixture schema until the
    adversarial review pointed at it.

    A `timeout` is passed because `test_gate_crash_exit_code._run` passes one and
    this call site did not; a fixtured gate that hangs would otherwise hang the CI
    job with no diagnostic.
    """
    argv = [str(scripts / gate)] + [a.replace("{dir}", str(case["_dir"])) for a in case["argv"]]
    proc = subprocess.run(  # noqa: S603
        [sys.executable] + argv,
        capture_output=True,
        text=True,
        # BOTH ends pinned, and one alone is worse than neither.
        #
        # `text=True` alone decodes with the ANSI codepage on Windows, so a
        # gate printing an em dash, a section sign or a curly quote comes back
        # mojibake and silently stops matching its fixture.
        #
        # Adding `encoding="utf-8"` alone is WORSE: the child still WRITES
        # cp1252, so decoding raises UnicodeDecodeError inside subprocess's
        # reader THREAD, which swallows it and hands back an EMPTY string with
        # a normal return code. Measured on
        # `check_audit_evidence/2026-08-empty-changed-file-list`: 96 chars and
        # the expected phrase became 0 chars and a failed contract, with no
        # error surfacing to this caller. A decode failure that reads as "the
        # gate printed nothing" is the silent-success shape in the harness
        # built to find it.
        #
        # `PYTHONIOENCODING` makes the child EMIT utf-8, so the two ends agree
        # by construction rather than by the platform defaults happening to
        # match -- derivation over synchronization.
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        encoding="utf-8",
        timeout=120,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _contract_failures(gate: str, cases: list[dict]) -> list[str]:
    out: list[str] = []
    if not [c for c in cases if int(c["expect"]) == 0]:
        out.append(f"{gate}: no case that the gate passes")
    if not [c for c in cases if int(c["expect"]) == 1]:
        out.append(
            f"{gate}: NO NEGATIVE CONTROL -- no case expects exit 1, so these "
            f"fixtures prove the gate runs, not that it discriminates"
        )
    # Exit 1 and exit 2 are the two codes D-051 exists to keep apart, so the
    # negative control must be a 1 specifically. `!= 0` admitted a 2, which would
    # have let a gate be "covered" by fixtures proving only that it can refuse to
    # look -- the two branches merged, inside the gate whose organising principle
    # is that they never share one. Latent when found: all four covered gates
    # already had a 1.
    for case in [c for c in cases if int(c["expect"]) == 2 and not c.get("stdout_contains")]:
        out.append(
            f"{gate}/{case['_dir'].name}: expects exit 2 without stdout_contains "
            f"-- a gate has several 'could not look' branches and the code alone "
            f"cannot say which one fired"
        )
    if not [c for c in cases if int(c["expect"]) == 2]:
        out.append(
            f"{gate}: no case expects exit 2 -- the fail-closed half of this "
            f"gate ('I could not look') is unfixtured"
        )
    if not [c for c in cases if c.get("adversarial")]:
        out.append(
            f"{gate}: no case marked adversarial -- ordinary cases test the "
            f"rule, adversarial cases test the boundary"
        )
    return out


def main(argv: list[str]) -> int:
    default_root = Path(__file__).resolve().parents[1] / "tests" / "gates"
    root = Path(argv[1]).resolve() if len(argv) > 1 else default_root
    if not root.is_dir():
        print(f"check-gate-fixtures: fixture root not found: {root}")
        return 2
    scripts = scripts_dir_for(root)
    if not scripts.is_dir():
        print(f"check-gate-fixtures: no scripts directory beside {root}")
        return 2

    gates = discover_gates(scripts)
    if not gates:
        print(f"check-gate-fixtures: no check_*.py discovered under {scripts}")
        return 2

    unknown = sorted(set(DEFERRED) - set(gates))
    if unknown:
        print("check-gate-fixtures: DEFERRED names gates that do not exist:")
        for name in unknown:
            print(f"  {name}")
        return 2

    failures: list[str] = []
    unreadable: list[str] = []
    gaps: list[str] = []
    checked = 0

    for gate in gates:
        gate_dir = root / gate.removesuffix(".py")
        if not gate_dir.is_dir():
            if gate not in DEFERRED:
                failures.append(f"{gate}: no fixtures and not in DEFERRED")
            continue
        if gate in DEFERRED:
            failures.append(f"{gate}: has fixtures AND is in DEFERRED -- pick one")
            continue

        cases, problems = load_cases(gate_dir)
        unreadable += [f"{gate}/{p}" for p in problems]
        if problems:
            continue
        if not cases:
            unreadable.append(f"{gate}: fixture directory contains no cases")
            continue

        failures += _contract_failures(gate, cases)

        for case in cases:
            checked += 1
            want = int(case["expect"])
            got, output = run_case(scripts, gate, case)
            name = case["_dir"].name
            if got != want:
                failures.append(
                    f"{gate}/{name}: expected exit {want}, got {got} "
                    f"[incident: {case['incident']}]"
                )
            needle = case.get("stdout_contains")
            if needle and needle not in output:
                failures.append(
                    f"{gate}/{name}: exit {got} was correct but the output does "
                    f"not contain {needle!r} -- the case may be passing from a "
                    f"different branch than it names"
                )
            gap = case.get("gap")
            if gap:
                gaps.append(
                    f"{gate}/{name}: returns {want}, should return "
                    f"{gap.get('should_be')} -- {gap.get('issue')}"
                )

    for line in gaps:
        print(f"check-gate-fixtures: KNOWN GAP {line}")

    if unreadable:
        print("check-gate-fixtures: could not read fixtures (exit 2, NOT a pass):")
        for line in unreadable:
            print(f"  {line}")
        return 2
    if failures:
        print("check-gate-fixtures: FAILED")
        for line in failures:
            print(f"  {line}")
        return 1

    covered = len(gates) - len(DEFERRED)
    print(
        f"check-gate-fixtures: {checked} cases across {covered} gates behaved as "
        f"specified ({len(DEFERRED)} deferred with reasons)"
    )
    return 0


if __name__ == "__main__":
    # A crash must not share an exit code with "found something": Python exits 1
    # on an unhandled exception, which is this gate's violation code.
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        # KeyboardInterrupt re-raised, NOT relabelled 2. Every other gate does
        # this, and `test_gate_crash_exit_code` forbids the alternative for all
        # of them: reporting Ctrl-C as "I could not look" is a verdict the user
        # never asked for. This file deviated until the adversarial review of
        # PR #216 read the nine and then read this one.
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        # stderr, not stdout: the success line goes to stdout, and a crash notice
        # sharing that stream is one grep away from being read as output.
        print(f"check-gate-fixtures: CRASHED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

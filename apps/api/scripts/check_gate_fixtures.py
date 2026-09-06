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
  * at least one case the gate FAILS (non-zero) -- the NEGATIVE CONTROL, without
    which the suite proves the gate runs and not that it discriminates;
  * at least one case marked `adversarial`: input a reasonable person would
    expect to pass, that must not. Ordinary cases test the rule; adversarial
    cases test the boundary, and the boundary is where all of these have broken.

Every case names the INCIDENT it derives from. A fixture that cannot be traced
to a recorded incident was derived from the rule rather than from the failure --
the inversion that produced the defects above -- and is rejected here.

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
import subprocess
import sys
from pathlib import Path

# Gates knowingly without fixtures, each with its reason. A gate in neither this
# mapping nor the fixture tree FAILS the run: silence must not be how coverage
# quietly shrinks.
DEFERRED: dict[str, str] = {
    "check_issue_references.py": (
        "reads a PR title, body and commit messages rather than files on disk; "
        "its input model needs a different harness than a fixture directory"
    ),
    "check_audit_evidence.py": (
        "reads a PR body and a changed-file list -- the same input-model mismatch"
    ),
    "check_separator_classes.py": (
        "reads one named module on the egress path, so a fixture would be a "
        "stand-in redact.py; a stand-in for the file whose realness is the whole "
        "point is worth less than the incident that would justify writing it"
    ),
}

_SELF = "check_gate_fixtures.py"
_REQUIRED_KEYS = ("incident", "expect", "argv")


def scripts_dir_for(root: Path) -> Path:
    """The scripts directory beside a fixture root at <api>/tests/gates."""
    return root.parents[1] / "scripts"


def discover_gates(scripts: Path) -> list[str]:
    return sorted(p.name for p in scripts.glob("check_*.py") if p.name != _SELF)


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


def run_case(scripts: Path, gate: str, case: dict) -> int:
    argv = [str(scripts / gate)] + [a.replace("{dir}", str(case["_dir"])) for a in case["argv"]]
    proc = subprocess.run(  # noqa: S603
        [sys.executable] + argv,
        capture_output=True,
        text=True,
    )
    return proc.returncode


def _contract_failures(gate: str, cases: list[dict]) -> list[str]:
    out: list[str] = []
    if not [c for c in cases if int(c["expect"]) == 0]:
        out.append(f"{gate}: no case that the gate passes")
    if not [c for c in cases if int(c["expect"]) != 0]:
        out.append(
            f"{gate}: NO NEGATIVE CONTROL -- every case expects 0, so these "
            f"fixtures prove the gate runs, not that it discriminates"
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
            got = run_case(scripts, gate, case)
            name = case["_dir"].name
            if got != want:
                failures.append(
                    f"{gate}/{name}: expected exit {want}, got {got} "
                    f"[incident: {case['incident']}]"
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
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001
        print(f"check-gate-fixtures: CRASHED: {type(exc).__name__}: {exc}")
        raise SystemExit(2) from exc

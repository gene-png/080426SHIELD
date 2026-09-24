"""Every test in `tests/unit` must be one CI actually runs (#540).

WHY THIS EXISTS. A test that exists, is believed to run, and does not is worse
than a vacuous one, because a vacuous test at least reports. Two instances on
2026-09-24: the #535/#536 leak tests shipped with no `unit` mark, so CI's
`pytest -m unit tests/unit` would have selected 0 of their 61 tests while every
local run -- which named the file directly -- passed; and #483, Playwright specs
gated on variables no workflow sets (`check_e2e_env_gates.py` is that half).
`check_test_integrity.py` catches tests that cannot fail. Nothing caught tests
that never run.

WHAT IT DOES. Collects `tests/unit` twice with the real pytest, once with CI's
exact selector (`CI_SELECTOR`) and once with none, and compares per file. Every
test collected but not selected is a finding, unless the file is in the
baseline with a count and a REASON. The baseline ratchets: a file whose
unselected count grew is a finding, and so is one that SHRANK -- lower the
entry or delete it, so the backlog is visible and only ever goes down.

WHY IT RUNS PYTEST RATHER THAN READING MARKS. The question is what CI's
selector selects, and only the selector can answer it: a mark can come from a
module `pytestmark`, a class, a decorator, a conftest hook or a plugin. Reading
source would be a second implementation of pytest's selection, free to drift.
`test_the_gates_selector_is_the_one_ci_runs` pins `CI_SELECTOR` to ci.yml.

EXIT CODES (D-051): 0 every collected test is selected or baselined; 1 at
least one finding; 2 could not look -- the collector failed, collected nothing,
printed a format this does not parse, the baseline is missing or malformed, or
an argument is unknown. An empty or unreadable collection is NEVER clean: the
first count behind this gate grepped `::` against `file: N` output and read
zero for everything.

LIMITS. Only `tests/unit`; `tests/live` is opt-in by design. A test that is
selected but SKIPS at runtime is not seen here (a runtime skip is not a
selection question).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

CI_SELECTOR = ("-m", "unit", "tests/unit")
_ALL = ("tests/unit",)

_COUNT_LINE = re.compile(r"^(?P<file>\S+\.py): (?P<n>\d+)$")
_NODE_LINE = re.compile(r"^(?P<file>\S+\.py)::\S")


def parse_collection(output: str) -> dict[str, int]:
    """Per-file test counts from `pytest --collect-only -q`, in either format.

    pytest prints `path: N` per file in quiet collect mode on this version and
    node ids (`path::name`) on others. Anything else is ignored, so output in
    neither format parses to {} -- which the caller treats as could-not-look,
    never as "zero tests".
    """
    counts: dict[str, int] = {}
    for raw in output.splitlines():
        line = raw.strip().replace("\\", "/")
        m = _COUNT_LINE.match(line)
        if m:
            counts[m.group("file")] = counts.get(m.group("file"), 0) + int(m.group("n"))
            continue
        m = _NODE_LINE.match(line)
        if m:
            counts[m.group("file")] = counts.get(m.group("file"), 0) + 1
    return counts


class CouldNotLook(Exception):
    """The gate could not establish the answer. Maps to exit 2, never 0 or 1."""


def _collect(root: Path, args: tuple[str, ...]) -> dict[str, int]:
    proc = subprocess.run(  # noqa: S603  # nosec B603 - fixed argv, no untrusted input
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    # 5 = "no tests collected" for the selected run is legitimate only if the
    # unselected run also collects nothing, which the caller refuses anyway.
    if proc.returncode not in (0, 5):
        raise CouldNotLook(
            f"`pytest --collect-only {' '.join(args)}` exited {proc.returncode} in {root}:\n"
            + (proc.stdout + proc.stderr).strip()[-2000:]
        )
    return parse_collection(proc.stdout)


def _load_baseline(path: Path) -> dict[str, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CouldNotLook(f"cannot read baseline {path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(data, dict):
        raise CouldNotLook(f"baseline {path} must be a JSON object")
    for name, entry in data.items():
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("unselected"), int)
            or not str(entry.get("reason", "")).strip()
        ):
            raise CouldNotLook(
                f"baseline entry {name!r} needs an integer `unselected` and a non-empty `reason`"
            )
    return data


def evaluate(
    everything: dict[str, int], selected: dict[str, int], baseline: dict[str, dict]
) -> tuple[list[str], list[str]]:
    """(findings, allowed) -- allowed lines are printed on every run."""
    findings: list[str] = []
    allowed: list[str] = []
    for file in sorted(set(everything) | set(baseline)):
        total = everything.get(file, 0)
        gap = total - selected.get(file, 0)
        entry = baseline.get(file)
        if entry is None:
            if gap > 0:
                findings.append(
                    f"{file}: {gap} of {total} tests are never run by CI "
                    f"(`pytest {' '.join(CI_SELECTOR)}` does not select them). Mark them, "
                    "or baseline the file with a reason."
                )
            continue
        allowed_n = entry["unselected"]
        if gap > allowed_n:
            findings.append(
                f"{file}: {gap} of {total} tests unselected, but the baseline allows "
                f"{allowed_n} -- the backlog GREW."
            )
        elif gap < allowed_n:
            findings.append(
                f"{file}: {gap} unselected, baseline says {allowed_n} -- shrink the "
                "baseline entry (or delete it at 0), so the backlog only goes down."
            )
        else:
            allowed.append(f"{file}: {gap} of {total} unselected, baselined: {entry['reason']}")
    return findings, allowed


def _parse(argv: list[str]) -> tuple[Path, Path]:
    root, baseline = Path("."), Path("../../.github/ci-selection-baseline.json")
    args = list(argv[1:])
    while args:
        flag = args.pop(0)
        if flag == "--root" and args:
            root = Path(args.pop(0))
        elif flag == "--baseline" and args:
            baseline = Path(args.pop(0))
        else:
            raise CouldNotLook(f"unknown or incomplete argument: {flag!r}")
    return root, baseline


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        root, baseline_path = _parse(argv)
        if not (root / "tests" / "unit").is_dir():
            raise CouldNotLook(f"{root / 'tests' / 'unit'} does not exist -- wrong directory?")
        baseline = _load_baseline(baseline_path)
        everything = _collect(root, _ALL)
        selected = _collect(root, CI_SELECTOR)
        if not everything:
            raise CouldNotLook(
                "collected ZERO tests, or printed a format this does not parse -- "
                "an empty collection is not a clean one"
            )
    except CouldNotLook as exc:
        print(f"check-ci-selection: could not look -- {exc}")
        return 2

    findings, allowed = evaluate(everything, selected, baseline)
    total, chosen = sum(everything.values()), sum(selected.values())
    for line in allowed:
        print(f"  baselined: {line}")
    if findings:
        print(f"check-ci-selection: {len(findings)} finding(s); CI selects {chosen} of {total}:")
        for line in findings:
            print(f"  {line}")
        return 1
    print(f"check-ci-selection: clean -- CI selects {chosen} of {total} collected tests.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-ci-selection: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(2) from exc

"""Every test in `tests/unit` must be one CI actually runs (#540).

WHY THIS EXISTS. A test that exists, is believed to run, and does not is worse
than a vacuous one, because a vacuous test at least reports. Both instances
turned up on 2026-09-24: the #535/#536 leak tests shipped with no `unit` mark,
so CI's `pytest -m unit tests/unit` would have selected 0 of their 61 tests
while every local run -- which named the file directly -- passed; and #483,
Playwright specs gated on variables no workflow sets (`check_e2e_env_gates.py`
is that half). `check_test_integrity.py` catches tests that cannot fail.
Nothing caught tests that never run.

WHAT IT DOES. Collects `tests/unit` twice with the real pytest -- once with
CI's exact selector (`CI_SELECTOR`), once with none -- as NODE IDS, and every
test collected but not selected is a finding unless its node id is in the
baseline under a file entry with a REASON.

WHY NODE IDS, NOT COUNTS. A per-file count let a new never-run test replace
an old one with no finding: mark one, add another, the count stays the same
(review of e8424dd). Each unselected test is named, so one cannot stand in for
another.

THE BASELINE RATCHETS. A baselined node id that is now selected, or no longer
exists, is a finding too: delete it from the baseline, so the backlog is
visible and only ever goes down.

WHY IT RUNS PYTEST RATHER THAN READING MARKS. The question is what CI's
selector selects, and only the selector can answer it: a mark can come from a
module `pytestmark`, a class, a decorator, a conftest hook or a plugin. Reading
source would be a second implementation of pytest's selection, free to drift.
`CI_SELECTOR` is pinned to ci.yml's exact `run:` line by a test that parses
the workflow and requires equality, not a substring -- a `-k` or `--deselect`
appended in CI would otherwise narrow CI while this certified the wider set.

THE SELECTED SET IS PYTEST'S OWN ANSWER, NOT A RECONSTRUCTION OF IT. The
selected collection runs CI's exact argv with the configuration LEFT ALONE, so
whatever pytest applies -- addopts in whichever config file it finds (`pytest.toml`,
`pytest.ini`, `pyproject.toml` in ini or native `[tool.pytest]` form, `tox.ini`,
`setup.cfg`, in any directory it walks), `PYTEST_ADDOPTS`, conftest hooks --
narrows this set exactly as it narrows CI. A small probe plugin
(`_PROBE_SOURCE`, loaded with `-p`) writes `session.items` to a file, so the
answer does not depend on how stdout is formatted. An earlier version cleared
addopts to get a parseable stdout and then tried to READ the config to make up
for it; review of adaf082 showed pytest looks in more places than any reader
of named files would (the reason this is a derivation now).

The "everything" collection clears addopts (`-o addopts=`) AND removes
`PYTEST_ADDOPTS` from its environment, because a `--deselect` or `-k` in
either is exactly what it must not inherit. `-o addopts=` alone does not
reach the variable: pytest prepends it to the arguments before the ini is
read (review of 701f032).

EXIT CODES (D-051): 0 every collected test is selected or baselined; 1 at
least one finding; 2 could not look -- the collector failed (including a
configured option this cannot honour, e.g. `--lf` with the cache disabled),
the probe reported nothing, the unselected collection is empty, the baseline
is missing or malformed, or an argument is unknown. An empty or unreadable collection is NEVER clean.

LIMITS. Only `tests/unit`; `tests/live` is opt-in by design. A test that is
selected but SKIPS at runtime is not seen here (a runtime skip is not a
selection question). A module-level `pytest.skip(..., allow_module_level=True)`
removes the file from BOTH collections, so it shrinks the denominator rather
than producing a finding. A conftest hook that deselects applies to BOTH
collections, so it is invisible too. `PYTEST_ADDOPTS` or other environment
set on CI's pytest step but not on this one is not seen.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CI_SELECTOR = ("-m", "unit", "tests/unit")
_ALL = ("tests/unit",)

_PROBE_NAME = "_ci_selection_probe"
_PROBE_OUT = "CHECK_CI_SELECTION_OUT"
_PROBE_SOURCE = f"""\
import os


def pytest_collection_finish(session):
    with open(os.environ["{_PROBE_OUT}"], "w", encoding="utf-8") as fh:
        fh.write("\\n".join(item.nodeid for item in session.items))
"""


class CouldNotLook(Exception):
    """The gate could not establish the answer. Maps to exit 2, never 0 or 1."""


def _collect(root: Path, args: tuple[str, ...], *, clear_addopts: bool) -> set[str]:
    """Node ids pytest collects for `args`, as reported by the probe plugin."""
    with tempfile.TemporaryDirectory() as tmp:
        probe_dir = Path(tmp)
        (probe_dir / f"{_PROBE_NAME}.py").write_text(_PROBE_SOURCE, encoding="utf-8")
        out = probe_dir / "ids.txt"
        env = dict(os.environ)
        env[_PROBE_OUT] = str(out)
        if clear_addopts:
            env.pop("PYTEST_ADDOPTS", None)
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [tmp, env.get("PYTHONPATH")]))
        clear = ("-o", "addopts=") if clear_addopts else ()
        cmd = [
            sys.executable, "-m", "pytest", "--collect-only", "-p", "no:cacheprovider",
            "-p", _PROBE_NAME, *clear, *args,
        ]  # fmt: skip
        proc = subprocess.run(  # noqa: S603  # nosec B603 - fixed argv, no untrusted input
            cmd, cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", check=False
        )
        # 5 = no tests collected: legitimate for the SELECTED run (every test then
        # becomes a finding), and refused for the unselected run by the caller.
        if proc.returncode not in (0, 5):
            raise CouldNotLook(
                f"`pytest --collect-only {' '.join(clear + args)}` exited {proc.returncode} "
                f"in {root}:\n" + (proc.stdout + proc.stderr).strip()[-2000:]
            )
        if not out.is_file():
            raise CouldNotLook(
                f"the probe plugin wrote nothing for `{' '.join(args)}` -- it did not load, "
                "so there is no answer to read"
            )
        return {line for line in out.read_text(encoding="utf-8").splitlines() if line}


def _load_baseline(path: Path) -> dict[str, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CouldNotLook(f"cannot read baseline {path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(data, dict):
        raise CouldNotLook(f"baseline {path} must be a JSON object")
    for name, entry in data.items():
        tests = entry.get("tests") if isinstance(entry, dict) else None
        if (
            not isinstance(entry, dict)
            or not str(entry.get("reason", "")).strip()
            or not isinstance(tests, list)
            or not tests
            or not all(isinstance(t, str) and t.startswith(f"{name}::") for t in tests)
        ):
            raise CouldNotLook(
                f"baseline entry {name!r} needs a non-empty `reason` and a non-empty "
                f"`tests` list of node ids under {name}::"
            )
    return data


def evaluate(
    everything: set[str], selected: set[str], baseline: dict[str, dict]
) -> tuple[list[str], list[str]]:
    """(findings, allowed) -- allowed lines are printed on every run."""
    unselected = everything - selected
    baselined = {t: f for f, e in baseline.items() for t in e["tests"]}
    findings: list[str] = []
    new = sorted(unselected - set(baselined))
    for test in new:
        findings.append(
            f"{test}: CI never runs it (`pytest {' '.join(CI_SELECTOR)}` does not select "
            "it). Mark it, or baseline it with a reason."
        )
    for test in sorted(set(baselined) - unselected):
        state = "now selected" if test in selected else "no longer exists"
        findings.append(
            f"{test}: baselined, but {state} -- delete it from the baseline so the "
            "backlog only goes down."
        )
    allowed = [
        f"{f}: {len([t for t in e['tests'] if t in unselected])} never-run test(s), "
        f"baselined: {e['reason']}"
        for f, e in sorted(baseline.items())
    ]
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
        everything = _collect(root, _ALL, clear_addopts=True)
        selected = _collect(root, CI_SELECTOR, clear_addopts=False)
        if not everything:
            raise CouldNotLook(
                "collected ZERO tests with no selector. An empty collection is not a " "clean one."
            )
    except CouldNotLook as exc:
        print(f"check-ci-selection: could not look -- {exc}")
        return 2

    findings, allowed = evaluate(everything, selected, baseline)
    for line in allowed:
        print(f"  baselined: {line}")
    summary = f"CI selects {len(selected & everything)} of {len(everything)} collected tests"
    if findings:
        print(f"check-ci-selection: {len(findings)} finding(s); {summary}:")
        for line in findings:
            print(f"  {line}")
        return 1
    print(f"check-ci-selection: clean -- {summary}.")
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

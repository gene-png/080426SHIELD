"""Prove CI's unit run ran the certified selection: each test once, none lost.

WHY. CI runs `pytest -m unit tests/unit` over four xdist workers on one runner
(`-n 4`). pytest's own summary line counts what the workers REPORTED, and a
worker that dies has its test re-run elsewhere or reported as an error, so a
green summary does not by itself say that every selected test ran exactly
once. `check_ci_selection.py --selected-out` writes the set it certified; this
holds the run's junit XML to that set, TEST BY TEST, never by the summary line.

    python -m scripts.check_junit_counts --junit FILE --selected FILE

A finding, each named: a selected test reported twice, or never reported; a
reported test that was not selected; and passed + skipped + xfailed short of
the selection (a failed or errored test is short by one -- pytest's own exit
is red too, and this says which count it took off). Skipped tests are counted
and NAMED: they were accounted for and did not run.

IDENTITY. pytest writes each testcase as (classname, name) from the node id:
`tests/unit/test_a.py::TestX::test_y[1]` becomes classname
`tests.unit.test_a.TestX`, name `test_y[1]` (`_pytest.junitxml`'s
`mangle_test_address`, read from pytest 9.1.1). `junit_id` reproduces that
from each selected node id. A pytest release that changes the mangling turns
every test into "never reported" and "not selected" at once -- loudly, never a
false clean.

Exit codes (D-090): 0 every selected test reported once, none short; 1 a
finding; 2 could not look -- an argument missing, a file missing or empty, the
XML unparseable or holding no testcase.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET  # noqa: S405 - pytest's own output, from this run
from collections import Counter
from pathlib import Path


class _CouldNotLook(Exception):
    pass


def junit_id(nodeid: str) -> tuple[str, str]:
    """(classname, name), as pytest's junitxml writes them for `nodeid`."""
    path, bracket, params = nodeid.partition("[")
    names = path.split("::")
    names[0] = re.sub(r"\.py$", "", names[0].replace("/", "."))
    names[-1] += bracket + params
    return ".".join(names[:-1]), names[-1]


def _outcome(case: ET.Element) -> str:
    """passed, failed, skipped or xfailed. pytest writes an xfail as a
    <skipped type="pytest.xfail">, an error or failure as its own child."""
    if case.find("failure") is not None or case.find("error") is not None:
        return "failed"
    skipped = case.find("skipped")
    if skipped is not None:
        return "xfailed" if skipped.get("type") == "pytest.xfail" else "skipped"
    return "passed"


def _read_selected(path: Path) -> list[str]:
    try:
        ids = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError as exc:
        raise _CouldNotLook(f"cannot read the selection {path}: {exc}") from exc
    if not ids:
        raise _CouldNotLook(f"the selection {path} is empty")
    return ids


def _read_cases(path: Path) -> list[tuple[tuple[str, str], str]]:
    try:
        root = ET.parse(path).getroot()  # noqa: S314 - pytest's own output, from this run
    except (OSError, ET.ParseError) as exc:
        raise _CouldNotLook(f"cannot read the junit XML {path}: {exc}") from exc
    cases = [
        ((c.get("classname", ""), c.get("name", "")), _outcome(c)) for c in root.iter("testcase")
    ]
    if not cases:
        raise _CouldNotLook(f"the junit XML {path} holds no testcase")
    return cases


def evaluate(selected: list[str], cases: list[tuple[tuple[str, str], str]]) -> tuple[list[str], dict]:
    """Findings, and the counts by outcome."""
    wanted = {junit_id(nodeid): nodeid for nodeid in selected}
    seen = Counter(key for key, _ in cases)
    counts = Counter(outcome for _, outcome in cases)
    findings = [
        f"reported {n} times: {wanted.get(key, '::'.join(key))}"
        for key, n in sorted(seen.items())
        if n > 1
    ]
    findings += [
        f"selected but never reported: {nodeid}"
        for key, nodeid in sorted(wanted.items(), key=lambda kv: kv[1])
        if key not in seen
    ]
    findings += [
        f"reported but not selected: {'::'.join(key)}"
        for key in sorted(seen)
        if key not in wanted
    ]
    accounted = counts["passed"] + counts["skipped"] + counts["xfailed"]
    if accounted < len(selected):
        findings.append(
            f"passed + skipped + xfailed is {accounted}, short of the {len(selected)} selected "
            f"({counts['failed']} failed or errored)"
        )
    return findings, counts


def _parse(argv: list[str]) -> dict[str, Path]:
    opts: dict[str, Path] = {}
    it = iter(argv[1:])
    for arg in it:
        if arg not in ("--junit", "--selected"):
            raise _CouldNotLook(f"unexpected argument {arg!r}")
        value = next(it, None)
        if value is None:
            raise _CouldNotLook(f"{arg} given with no value")
        opts[arg] = Path(value)
    if set(opts) != {"--junit", "--selected"}:
        raise _CouldNotLook("usage: check_junit_counts --junit FILE --selected FILE")
    return opts


def main(argv: list[str]) -> int:
    try:
        opts = _parse(argv)
        selected = _read_selected(opts["--selected"])
        cases = _read_cases(opts["--junit"])
    except _CouldNotLook as exc:
        print(f"check-junit-counts: could not look -- {exc}")
        return 2
    findings, counts = evaluate(selected, cases)
    print(
        f"check-junit-counts: {len(selected)} selected; junit reports {len(cases)}: "
        f"{counts['passed']} passed, {counts['skipped']} skipped, "
        f"{counts['xfailed']} xfailed, {counts['failed']} failed or errored"
    )
    skipped = sorted(
        "::".join(key) for key, outcome in cases if outcome == "skipped"
    )
    for name in skipped[:50]:
        print(f"  skipped, did not run: {name}")
    if len(skipped) > 50:
        print(f"  ... and {len(skipped) - 50} more skipped")
    if findings:
        print(f"check-junit-counts: {len(findings)} finding(s):")
        for line in findings[:50]:
            print(f"  {line}")
        if len(findings) > 50:
            print(f"  ... and {len(findings) - 50} more")
        return 1
    print("check-junit-counts: clean -- every selected test reported exactly once")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-junit-counts: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a verdict and not a finding (D-090).{nl}")
        raise SystemExit(2) from exc

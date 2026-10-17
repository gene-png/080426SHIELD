"""The required Python check's aggregate: both legs ran the one certified selection, once.

    python -m scripts.check_python_shards --dir DIR --of 2

CI's Python check runs the unit suite in `--of` legs (`shard_deselect.py`), and
each uploads three files, named for its index `k`: `selection-k.txt` (the set
`check_ci_selection.py` certified on that runner), `dealt-k.txt` (the ids that
leg was dealt) and `junit-k.xml` (what it ran). This holds the legs to each
other, and every finding is named:

    1. exactly `--of` files of each kind, indexed 1..of, none missing, none extra;
    2. the selections are byte for byte the same, so every leg dealt from one set;
    3. the dealt lists PARTITION that selection (`shard_partition.verify`);
    4. each leg's junit equals its OWN dealt list: nothing dealt was lost,
       nothing else ran, and every dealt test is passed, skipped or xfailed;
    5. the junits TOGETHER report every selected test exactly once, so a test in
       two junits is a duplicate, whatever the dealt lists say.

It prints each leg's pytest time from its junit, and says when they differ by
more than two minutes (a note, not a finding: the deal balances counts, not
time, and the plan is to deal by duration if the difference is real).

Exit codes (D-090): 0 clean; 1 a finding; 2 could not look -- an argument
missing or unknown, a file missing, empty or unreadable, a file of the wrong
index or count, or a junit that holds no testcase.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import xml.etree.ElementTree as ET  # noqa: S405 - pytest's own output, from this run
from pathlib import Path
from types import ModuleType

#: Legs further apart than this (seconds) are noted.
IMBALANCE_NOTE_SECONDS = 120.0
_KINDS = (("selection", "txt"), ("dealt", "txt"), ("junit", "xml"))


class _CouldNotLook(Exception):
    pass


def _sibling(stem: str) -> ModuleType:
    """Load `scripts/<stem>.py` BY PATH, so the identity rules and the partition
    check are the ones the legs themselves run, not a copy. By path rather than
    `import scripts.<stem>` because a gate script is also run as a bare file
    (`tests/unit/test_gate_crash_exit_code.py` does), where `scripts` is not on
    sys.path; an unloadable sibling is could-not-look, never a skipped check."""
    path = Path(__file__).with_name(f"{stem}.py")
    spec = importlib.util.spec_from_file_location(f"_check_python_shards_{stem}", path)
    if spec is None or spec.loader is None:
        raise _CouldNotLook(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, SyntaxError, ImportError) as exc:
        raise _CouldNotLook(f"cannot load {path}: {exc}") from exc
    return module


def _leg_files(directory: Path, of: int) -> dict[str, dict[int, Path]]:
    """{kind: {index: path}}, refusing a missing, extra or misnumbered file."""
    if not directory.is_dir():
        raise _CouldNotLook(f"{directory} is not a directory")
    found: dict[str, dict[int, Path]] = {}
    for kind, suffix in _KINDS:
        pattern = re.compile(rf"{kind}-(\d+)\.{suffix}")
        files = {}
        for path in sorted(directory.rglob(f"{kind}-*.{suffix}")):
            match = pattern.fullmatch(path.name)
            if not match:
                raise _CouldNotLook(f"{path} is not named {kind}-<index>.{suffix}")
            files.setdefault(int(match.group(1)), []).append(path)
        extra = {i: ps for i, ps in files.items() if len(ps) > 1}
        if extra:
            raise _CouldNotLook(f"two {kind} files for one index: {extra}")
        files = {i: ps[0] for i, ps in files.items()}
        if sorted(files) != list(range(1, of + 1)):
            raise _CouldNotLook(
                f"expected exactly {of} {kind} files, indexed 1 to {of}; found indexes {sorted(files)}"
            )
        found[kind] = files
    return found


def _ids(path: Path, label: str) -> list[str]:
    try:
        ids = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError as exc:
        raise _CouldNotLook(f"cannot read the {label} {path}: {exc}") from exc
    if not ids:
        raise _CouldNotLook(f"the {label} {path} is empty")
    return ids


def _seconds(path: Path) -> float:
    try:
        suite = next(ET.parse(path).getroot().iter("testsuite"))  # noqa: S314 - own output
        return float(suite.get("time", ""))
    except (OSError, ET.ParseError, StopIteration, ValueError) as exc:
        raise _CouldNotLook(f"cannot read a pytest time from {path}: {exc}") from exc


def check(directory: Path, of: int) -> tuple[list[str], list[str]]:
    """(findings, report lines) for the legs under `directory`."""
    shard_partition = _sibling("shard_partition")
    junit_counts = _sibling("check_junit_counts")
    files = _leg_files(directory, of)
    selections = {i: files["selection"][i].read_bytes() for i in files["selection"]}
    findings: list[str] = []
    if len(set(selections.values())) != 1:
        findings.append(
            "the legs certified DIFFERENT selections: "
            + ", ".join(f"leg {i} has {len(b.splitlines())} lines" for i, b in selections.items())
        )
    full = _ids(files["selection"][1], "selection")
    dealt = {i: _ids(files["dealt"][i], f"leg {i} dealt list") for i in range(1, of + 1)}
    findings += shard_partition.verify(full, [dealt[i] for i in sorted(dealt)])
    all_cases = []
    report = []
    seconds = {}
    for i in range(1, of + 1):
        try:
            cases = junit_counts._read_cases(files["junit"][i])
        except junit_counts._CouldNotLook as exc:
            raise _CouldNotLook(str(exc)) from exc
        leg_findings, counts = junit_counts.evaluate(dealt[i], cases)
        findings += [f"leg {i}: {line}" for line in leg_findings]
        all_cases += cases
        seconds[i] = _seconds(files["junit"][i])
        report.append(
            f"leg {i}: dealt {len(dealt[i])}, junit reports {len(cases)} "
            f"({counts['passed']} passed, {counts['skipped']} skipped, "
            f"{counts['xfailed']} xfailed, {counts['failed']} failed or errored), "
            f"pytest time {seconds[i]:.0f}s"
        )
    whole, _ = junit_counts.evaluate(full, all_cases)
    findings += [f"all legs together: {line}" for line in whole]
    spread = max(seconds.values()) - min(seconds.values())
    if spread > IMBALANCE_NOTE_SECONDS:
        report.append(
            f"NOTE: the legs differ by {spread:.0f}s (more than {IMBALANCE_NOTE_SECONDS:.0f}s); "
            "the deal balances counts, not time"
        )
    return findings, report


def _parse(argv: list[str]) -> tuple[Path, int]:
    opts: dict[str, str] = {}
    it = iter(argv[1:])
    for arg in it:
        if arg not in ("--dir", "--of"):
            raise _CouldNotLook(f"unexpected argument {arg!r}")
        value = next(it, None)
        if value is None:
            raise _CouldNotLook(f"{arg} given with no value")
        opts[arg] = value
    if set(opts) != {"--dir", "--of"}:
        raise _CouldNotLook("usage: check_python_shards --dir DIR --of N")
    if not opts["--of"].isascii() or not opts["--of"].isdigit() or int(opts["--of"]) < 1:
        raise _CouldNotLook(f"--of {opts['--of']!r} is not a whole number of at least 1")
    return Path(opts["--dir"]), int(opts["--of"])


def main(argv: list[str]) -> int:
    try:
        directory, of = _parse(argv)
        findings, report = check(directory, of)
    except _CouldNotLook as exc:
        print(f"check-python-shards: could not look -- {exc}")
        return 2
    for line in report:
        print(f"check-python-shards: {line}")
    if findings:
        print(f"check-python-shards: {len(findings)} finding(s):")
        for line in findings[:50]:
            print(f"  {line}")
        if len(findings) > 50:
            print(f"  ... and {len(findings) - 50} more")
        return 1
    print(f"check-python-shards: clean -- {of} legs, one certified selection, every test ran once")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-python-shards: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a verdict and not a finding (D-090).{nl}")
        raise SystemExit(2) from exc

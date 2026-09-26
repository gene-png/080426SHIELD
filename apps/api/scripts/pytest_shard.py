"""Run CI's unit selection in shards that PARTITION it, and prove they did.

WHY. `pytest -m unit tests/unit` was 22 of the Python job's 24 minutes on CI.
Split across parallel jobs it is a fraction of that -- but a split that loses a
test is a test CI never runs, the failure `check_ci_selection.py` (#540) exists
for, reached through the one door that gate cannot see: it certifies the
SELECTOR, and a shard narrows the selection by environment.

HOW THE SPLIT IS DERIVED. From collection, per TEST. The selected node ids are
sorted, grouped by file, and each file's tests are dealt round-robin across the
shards, starting at an offset equal to the file's index. One file held 5,473 of
the 8,673 selected tests when this was written, so dealing whole FILES could not
balance, and a timing table would be a second copy of the truth to keep in
step. Dealing within each file spreads every file -- fast or slow -- evenly.

    <!-- counted: check_ci_selection._collect(CI_SELECTOR) per file, 2026-09-26, at 36c242e -->

AS A PYTEST PLUGIN (`-p scripts.pytest_shard`), set by two environment variables:

    PYTEST_SHARD          "k/N", 1-based
    PYTEST_SHARD_RECORD   where to write the node ids this shard will run

The assignment runs `trylast`, after `-m unit` has deselected, so it partitions
exactly the selected set. The record is written at `pytest_collection_finish`
from `session.items`, so a later deselection by any other plugin is reflected in
it: the record says what RAN, not what was planned. A missing or malformed
setting, or a shard left with nothing to run, is a usage error -- never a run of
everything, and never a green run of nothing.

AS A COMMAND, for the aggregate job:

    python -m scripts.pytest_shard collect --out FULL
        writes CI's full selection, from `check_ci_selection`'s own collector
    python -m scripts.pytest_shard verify --full FULL --of N --ran R1 ... RN
        every selected test ran in exactly one shard, and nothing else ran

Exit codes (D-090): 0 a partition; 1 a gap, a duplicate, or a test outside the
selection, each named; 2 could not look -- an argument missing or unknown, a
record missing or empty, the full selection empty, or the wrong number of
records for `--of`.
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

SHARD_ENV = "PYTEST_SHARD"
RECORD_ENV = "PYTEST_SHARD_RECORD"

_SPEC = re.compile(r"([1-9][0-9]*)/([1-9][0-9]*)")


class ShardSpecError(ValueError):
    """The shard setting is not `k/N` with 1 <= k <= N."""


def parse_spec(spec: str) -> tuple[int, int]:
    match = _SPEC.fullmatch(spec)
    if match is None:
        raise ShardSpecError(f"{SHARD_ENV} must be k/N, got {spec!r}")
    k, n = int(match.group(1)), int(match.group(2))
    if k > n:
        raise ShardSpecError(f"{SHARD_ENV}={spec!r}: shard {k} of only {n}")
    return k, n


def assign(nodeids: list[str], n: int) -> dict[str, int]:
    """The 1-based shard of every node id: per file, round-robin, offset by file."""
    files = sorted({nodeid.split("::", 1)[0] for nodeid in nodeids})
    offset = {path: index for index, path in enumerate(files)}
    dealt: dict[str, int] = defaultdict(int)
    shards: dict[str, int] = {}
    for nodeid in sorted(nodeids):
        path = nodeid.split("::", 1)[0]
        shards[nodeid] = (offset[path] + dealt[path]) % n + 1
        dealt[path] += 1
    return shards


# --- the plugin ------------------------------------------------------------------


def _setting() -> tuple[int, int, Path]:
    try:
        k, n = parse_spec(os.environ.get(SHARD_ENV, ""))
    except ShardSpecError as exc:
        raise pytest.UsageError(f"pytest_shard: {exc}") from exc
    record = os.environ.get(RECORD_ENV, "")
    if not record:
        raise pytest.UsageError(f"pytest_shard: {RECORD_ENV} is not set, so what ran is unrecorded")
    return k, n, Path(record)


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    k, n, _ = _setting()
    shards = assign([item.nodeid for item in items], n)
    keep = [item for item in items if shards[item.nodeid] == k]
    drop = [item for item in items if shards[item.nodeid] != k]
    if not keep:
        raise pytest.UsageError(
            f"pytest_shard: shard {k}/{n} selected no tests from {len(items)} -- "
            "a shard that runs nothing would pass, so it is refused"
        )
    config.stash[_SELECTED] = len(items)
    config.hook.pytest_deselected(items=drop)
    items[:] = keep


_SELECTED = pytest.StashKey[int]()


def pytest_collection_finish(session: pytest.Session) -> None:
    k, n, record = _setting()
    record.write_text("".join(f"{item.nodeid}\n" for item in session.items), encoding="utf-8")


def pytest_report_collectionfinish(config: pytest.Config, items: list[pytest.Item]) -> str:
    k, n, record = _setting()
    return f"pytest_shard: shard {k}/{n} kept {len(items)} of {config.stash[_SELECTED]} selected tests; recorded in {record}"


# --- the command -----------------------------------------------------------------


class _CouldNotLook(Exception):
    pass


def _read_ids(path: Path, label: str) -> list[str]:
    try:
        ids = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError as exc:
        raise _CouldNotLook(f"cannot read {label} {path}: {exc}") from exc
    if not ids:
        raise _CouldNotLook(f"{label} {path} is empty")
    return ids


def verify(full: list[str], records: list[list[str]]) -> list[str]:
    """Findings: every selected test must run in exactly one shard."""
    ran = Counter(nodeid for record in records for nodeid in record)
    selected = set(full)
    findings = [
        f"ran in {count} shards: {nodeid}" for nodeid, count in sorted(ran.items()) if count > 1
    ]
    findings += [
        f"selected but ran in no shard: {nodeid}" for nodeid in sorted(selected - set(ran))
    ]
    findings += [f"ran but not selected: {nodeid}" for nodeid in sorted(set(ran) - selected)]
    return findings


def _collect_full(out: Path) -> int:
    from scripts.check_ci_selection import CI_SELECTOR, CouldNotLook, _collect

    try:
        ids = _collect(Path.cwd(), CI_SELECTOR, clear_addopts=False)
    except CouldNotLook as exc:
        print(f"pytest_shard collect: could not look -- {exc}")
        return 2
    if not ids:
        print("pytest_shard collect: could not look -- the selection is empty")
        return 2
    out.write_text("".join(f"{nodeid}\n" for nodeid in sorted(ids)), encoding="utf-8")
    print(f"pytest_shard collect: {len(ids)} selected tests written to {out}")
    return 0


def _parse(argv: list[str]) -> tuple[str, dict[str, list[str]]]:
    if len(argv) < 2 or argv[1] not in ("collect", "verify"):
        raise _CouldNotLook(
            "usage: pytest_shard collect --out FILE | verify --full FILE --of N --ran FILE..."
        )
    opts: dict[str, list[str]] = defaultdict(list)
    current = None
    for arg in argv[2:]:
        if arg in ("--out", "--full", "--of", "--ran"):
            current = arg
        elif current is None:
            raise _CouldNotLook(f"unexpected argument {arg!r}")
        else:
            opts[current].append(arg)
    return argv[1], opts


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    try:
        command, opts = _parse(argv)
        if command == "collect":
            if len(opts["--out"]) != 1:
                raise _CouldNotLook("collect needs exactly one --out")
            return _collect_full(Path(opts["--out"][0]))
        if len(opts["--full"]) != 1 or not opts["--ran"]:
            raise _CouldNotLook("verify needs one --full and at least one --ran")
        full = _read_ids(Path(opts["--full"][0]), "the full selection")
        records = [_read_ids(Path(p), "shard record") for p in opts["--ran"]]
        if opts["--of"] and [str(len(records))] != opts["--of"]:
            raise _CouldNotLook(
                f"--of {' '.join(opts['--of'])} but {len(records)} shard records were given"
            )
    except _CouldNotLook as exc:
        print(f"pytest_shard: could not look -- {exc}")
        return 2
    findings = verify(full, records)
    if findings:
        print(
            f"pytest_shard verify: the shards are NOT a partition of the {len(full)} selected tests:"
        )
        for finding in findings[:50]:
            print(f"  {finding}")
        if len(findings) > 50:
            print(f"  ... and {len(findings) - 50} more")
        return 1
    print(
        f"pytest_shard verify: {len(full)} of {len(full)} selected tests ran in exactly one of {len(records)} shards"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

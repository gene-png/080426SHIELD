"""The partition behind CI's sharded unit run: assignment and verification.

Pure, and free of pytest, so the aggregate jobs can verify a partition without
installing the test stack. The pytest plugin that APPLIES the assignment is
`scripts/pytest_shard.py`, whose docstring says why the split is shaped this way.

Exit codes of the command (D-090): 0 a partition; 1 a gap, a duplicate, or an
id outside the full list, each named; 2 could not look -- an argument missing
or unknown, a record missing or empty, the full list empty, or the wrong number
of records for `--of`. The ids are opaque lines, so the same check verifies
pytest node ids and Playwright `--list` lines alike.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

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
    """Findings: every id in the full list must appear in exactly one record."""
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
        print(f"shard_partition collect: could not look -- {exc}")
        return 2
    if not ids:
        print("shard_partition collect: could not look -- the selection is empty")
        return 2
    out.write_text("".join(f"{nodeid}\n" for nodeid in sorted(ids)), encoding="utf-8")
    print(f"shard_partition collect: {len(ids)} selected tests written to {out}")
    return 0


def _parse(argv: list[str]) -> tuple[str, dict[str, list[str]]]:
    if len(argv) < 2 or argv[1] not in ("collect", "verify"):
        raise _CouldNotLook(
            "usage: shard_partition collect --out FILE | verify --full FILE --of N --ran FILE..."
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
        print(f"shard_partition: could not look -- {exc}")
        return 2
    findings = verify(full, records)
    if findings:
        print(
            f"shard_partition verify: the shards are NOT a partition of the {len(full)} selected tests:"
        )
        for finding in findings[:50]:
            print(f"  {finding}")
        if len(findings) > 50:
            print(f"  ... and {len(findings) - 50} more")
        return 1
    print(
        f"shard_partition verify: {len(full)} of {len(full)} selected tests ran in exactly one of {len(records)} shards"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

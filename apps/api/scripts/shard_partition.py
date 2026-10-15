"""The partition behind CI's sharded unit run: assignment and verification.

Pure, and free of pytest, so the aggregate jobs can verify a partition without
installing the test stack. The pytest plugin that APPLIES the assignment is
`scripts/pytest_shard.py`, whose docstring says why the split is shaped this way.

Exit codes of the command (D-090): 0 a partition; 1 a gap, a duplicate, or an
id outside the full list, each named; 2 could not look -- an argument missing
or unknown, a record missing or empty, the full list empty, or the wrong number
of records for `--of` (or of `--skipped` files for `--ran` records). The ids are
opaque lines, so the same check verifies pytest node ids and Playwright `--list`
lines alike.

`--skipped` (#689) takes the files the pytest plugin writes beside each record,
naming the tests that SKIPPED at runtime. A skipped test is accounted for -- it
is in the shard it was dealt to -- but it did not run, so it is counted and
named apart and never as a run. A skipped file may be empty; a missing one is
could-not-look. Playwright's lists are selections, not runs, and pass none.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SHARD_ENV = "PYTEST_SHARD"
RECORD_ENV = "PYTEST_SHARD_RECORD"

_SPEC = re.compile(r"([1-9][0-9]*)/([1-9][0-9]*)")


def skipped_path(record: Path) -> Path:
    """Where the plugin writes the ids a shard skipped, beside its record. The
    suffix keeps it out of a `pytest-shard-*.txt` glob over the records."""
    return Path(f"{record}.skipped")


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


def _read_ids(path: Path, label: str, *, may_be_empty: bool = False) -> list[str]:
    try:
        ids = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError as exc:
        raise _CouldNotLook(f"cannot read {label} {path}: {exc}") from exc
    if not ids and not may_be_empty:
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


def _parse(argv: list[str]) -> tuple[str, dict[str, list[str]]]:
    if len(argv) < 2 or argv[1] != "verify":
        raise _CouldNotLook(
            "usage: shard_partition verify --full FILE --of N --ran FILE... [--skipped FILE...]"
        )
    opts: dict[str, list[str]] = defaultdict(list)
    current = None
    for arg in argv[2:]:
        if arg in ("--full", "--of", "--ran", "--skipped"):
            current = arg
            opts[arg]  # noqa: B018 - a flag given with no values must still be seen
        elif current is None:
            raise _CouldNotLook(f"unexpected argument {arg!r}")
        else:
            opts[current].append(arg)
    empty = [flag for flag, values in opts.items() if not values]
    if empty:
        raise _CouldNotLook(f"{', '.join(empty)} given with no value")
    return argv[1], opts


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    try:
        _command, opts = _parse(argv)
        has_skipped = "--skipped" in opts  # read before any lookup adds the key
        if len(opts["--full"]) != 1 or not opts["--ran"]:
            raise _CouldNotLook("verify needs one --full and at least one --ran")
        full = _read_ids(Path(opts["--full"][0]), "the full selection")
        records = [_read_ids(Path(p), "shard record") for p in opts["--ran"]]
        if opts["--of"] and [str(len(records))] != opts["--of"]:
            raise _CouldNotLook(
                f"--of {' '.join(opts['--of'])} but {len(records)} shard records were given"
            )
        skipped = [_read_ids(Path(p), "skipped file", may_be_empty=True) for p in opts["--skipped"]]
        if has_skipped and len(skipped) != len(records):
            raise _CouldNotLook(
                f"{len(skipped)} skipped files for {len(records)} shard records; "
                "each shard writes one"
            )
    except _CouldNotLook as exc:
        print(f"shard_partition: could not look -- {exc}")
        return 2
    findings = verify(full, records + skipped)
    if findings:
        print(
            f"shard_partition verify: the shards are NOT a partition of the {len(full)} selected tests:"
        )
        for finding in findings[:50]:
            print(f"  {finding}")
        if len(findings) > 50:
            print(f"  ... and {len(findings) - 50} more")
        return 1
    if not has_skipped:
        print(
            f"shard_partition verify: {len(full)} of {len(full)} selected tests ran in exactly one of {len(records)} shards"
        )
        return 0
    skips = sorted(nodeid for record in skipped for nodeid in record)
    print(
        f"shard_partition verify: {len(full)} of {len(full)} selected tests are in exactly one of "
        f"{len(records)} shards: {len(full) - len(skips)} ran, {len(skips)} SKIPPED at runtime"
    )
    for nodeid in skips[:50]:
        print(f"  skipped, did not run: {nodeid}")
    if len(skips) > 50:
        print(f"  ... and {len(skips) - 50} more skipped")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"shard-partition: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a partition and not a finding (D-090).{nl}")
        raise SystemExit(2) from exc

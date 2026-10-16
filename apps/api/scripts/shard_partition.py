"""Verify that CI's E2E shards partition the Playwright suite.

The E2E suite runs in four legs, each with Playwright's own `--shard=k/4` and
its own composed stack. Each leg uploads its `--list` output, and the required
`E2E (Playwright smoke suite)` aggregate runs this over them against the full
`--list` the session job uploads: every listed test in exactly one shard, and
nothing else. Pure and free of pytest, so the aggregate needs no test stack.

What it checks is a SELECTION, not a run: a `--list` line says the shard was
dealt the test, and each leg's own exit status is what says the test passed.
(The pytest unit suite is not sharded; it runs on one runner under xdist, and
`check_junit_counts.py` holds that run to its selection.)

Exit codes of the command (D-090): 0 a partition; 1 a gap, a duplicate, or an
id outside the full list, each named; 2 could not look -- an argument missing
or unknown, a record missing or empty, the full list empty, or the wrong number
of records for `--of`. The ids are opaque lines.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

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


def _parse(argv: list[str]) -> tuple[str, dict[str, list[str]]]:
    if len(argv) < 2 or argv[1] != "verify":
        raise _CouldNotLook("usage: shard_partition verify --full FILE --of N --ran FILE...")
    opts: dict[str, list[str]] = defaultdict(list)
    current = None
    for arg in argv[2:]:
        if arg in ("--full", "--of", "--ran"):
            current = arg
        elif current is None:
            raise _CouldNotLook(f"unexpected argument {arg!r}")
        else:
            opts[current].append(arg)
    return argv[1], opts


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    try:
        _command, opts = _parse(argv)
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
        f"shard_partition verify: {len(full)} of {len(full)} selected tests are in exactly one of {len(records)} shard lists"
    )
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

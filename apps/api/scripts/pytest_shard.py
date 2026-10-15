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

AS A COMMAND, for the aggregate jobs, in the pytest-free `scripts/shard_partition.py`:

    python -m scripts.shard_partition verify --full FULL --of N --ran R1 ... RN
        every selected test ran in exactly one shard, and nothing else ran.
        FULL is the set `check_ci_selection --selected-out` wrote on a clean
        verdict -- the certified set itself, not a second collection.

Exit codes (D-090): 0 a partition; 1 a gap, a duplicate, or a test outside the
selection, each named; 2 could not look -- an argument missing or unknown, a
record missing or empty, the full selection empty, or the wrong number of
records for `--of`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.shard_partition import RECORD_ENV, SHARD_ENV, ShardSpecError, assign, parse_spec

__all__ = ["RECORD_ENV", "SHARD_ENV"]


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

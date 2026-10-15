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
    PYTEST_SHARD_RECORD   where to write the node ids this shard RAN; the ids it
                          SKIPPED go beside it, at `skipped_path(record)`

The assignment runs `trylast`, after `-m unit` has deselected, so it partitions
exactly the selected set. The records are written at `pytest_sessionfinish`
from each test's REPORTS, not from `session.items` (#689). Written from the
items, the record said what the shard SELECTED, so a test that skipped at
runtime read as run. Now a skipped test goes to the skipped file and not the
record, and a test with no report at all -- never reached after `-x`, an
interrupt or a crash -- is in neither, so the aggregate names it as selected
but run nowhere. Both files are deleted when collection finishes, so a record
left by an earlier run cannot stand in for this one; a session that never
finishes writes nothing, and the aggregate refuses a missing record. A missing
or malformed setting, or a shard left with nothing to run, is a usage error --
never a run of everything, and never a green run of nothing.

AS A COMMAND, for the aggregate jobs, in the pytest-free `scripts/shard_partition.py`:

    python -m scripts.shard_partition verify --full FULL --of N --ran R1 ... RN
                                             [--skipped S1 ... SN]
        every selected test is in exactly one shard's records, and nothing else
        is. With --skipped, a skipped test is counted and named APART from the
        ones that ran -- accounted for, never counted as run. FULL is the set
        `check_ci_selection --selected-out` wrote on a clean verdict -- the
        certified set itself, not a second collection.

Exit codes (D-090): 0 a partition; 1 a gap, a duplicate, or a test outside the
selection, each named; 2 could not look -- an argument missing or unknown, a
record missing or empty, the full selection empty, or the wrong number of
records for `--of`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.shard_partition import (
    RECORD_ENV,
    SHARD_ENV,
    ShardSpecError,
    assign,
    parse_spec,
    skipped_path,
)

__all__ = ["RECORD_ENV", "SHARD_ENV", "skipped_path"]


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
_COUNTS = pytest.StashKey[tuple[int, int, int]]()


def _is_skip(report: pytest.TestReport) -> bool:
    """A skip that kept the test body from running. An xfail is reported as
    skipped from the CALL phase with `wasxfail` set; its body ran, so it is not
    one. `xfail(run=False)` reports from SETUP and never runs, so it is."""
    return report.skipped and not (report.when == "call" and hasattr(report, "wasxfail"))


class _Outcomes:
    """Every node id pytest reported on, and those whose report was a skip."""

    def __init__(self) -> None:
        self.reported: set[str] = set()
        self.skipped: set[str] = set()

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        self.reported.add(report.nodeid)
        if _is_skip(report):
            self.skipped.add(report.nodeid)


_OUTCOMES = "pytest_shard_outcomes"


def pytest_configure(config: pytest.Config) -> None:
    config.pluginmanager.register(_Outcomes(), _OUTCOMES)


def pytest_collection_finish(session: pytest.Session) -> None:
    _, _, record = _setting()
    for path in (record, skipped_path(record)):
        path.unlink(missing_ok=True)


def pytest_sessionfinish(session: pytest.Session) -> None:
    config = session.config
    if _SELECTED not in config.stash:
        return  # the shard never got its tests, so nothing ran: write nothing
    _, _, record = _setting()
    outcomes: _Outcomes = config.pluginmanager.get_plugin(_OUTCOMES)
    ran = [
        item.nodeid
        for item in session.items
        if item.nodeid in outcomes.reported and item.nodeid not in outcomes.skipped
    ]
    skipped = [item.nodeid for item in session.items if item.nodeid in outcomes.skipped]
    record.write_text("".join(f"{nodeid}\n" for nodeid in ran), encoding="utf-8")
    skipped_path(record).write_text("".join(f"{nodeid}\n" for nodeid in skipped), encoding="utf-8")
    config.stash[_COUNTS] = (len(ran), len(skipped), len(session.items) - len(ran) - len(skipped))


def pytest_report_collectionfinish(config: pytest.Config, items: list[pytest.Item]) -> str:
    k, n, record = _setting()
    return f"pytest_shard: shard {k}/{n} kept {len(items)} of {config.stash[_SELECTED]} selected tests; recorded in {record}"


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    if _COUNTS not in config.stash:
        return
    ran, skipped, unreached = config.stash[_COUNTS]
    terminalreporter.write_line(
        f"pytest_shard: {ran} ran, {skipped} skipped at runtime, {unreached} never reached"
    )

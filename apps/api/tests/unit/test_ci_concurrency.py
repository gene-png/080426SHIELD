"""CI on `main` is never cancelled mid-run, and main's runs do not pile up.

History. `ci.yml` first grouped every run by `github.ref` with
`cancel-in-progress: true`, so merging the next PR cancelled the run testing the
previous one: the main runs for 7b396488, 779bba01, 1ab60b79, 25b34592 and
9b5623ba (2026-10-16) all ended `cancelled`. The fix that followed gave each
push its own group (the commit), which ended the cancelling but let every merge
start a full run of its own, so main's runs piled up.

Now (the advisor's block, #736 6217076147): the group is the ref again, and
only a pull request cancels a run in progress. So main has ONE group: a running
main run is never cancelled, and GitHub keeps at most one PENDING run behind it,
replacing an older pending one with the newest -- the newest commit is the one
worth testing. A pull request's superseded run is still cancelled.

Pinned by equality: the expression IS the behaviour, and GitHub evaluates it,
not this file.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from tests._paths import find_workflows_dir

pytestmark = pytest.mark.unit

#: Only a pull request cancels a run in progress; a push never does.
CANCEL = "${{ github.event_name == 'pull_request' }}"
#: One group per ref: a PR's ref, or main's.
GROUP = "${{ github.workflow }}-${{ github.ref }}"


def _ci() -> dict:
    wf = find_workflows_dir(pathlib.Path(__file__).resolve())
    if wf is None:
        # The api container mounts only apps/api. On a full checkout (CI) this
        # cannot fire: ci.yml's "the audit-gate tests must not skip on a full
        # checkout" step fails if find_workflows_dir returns None there.
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    return yaml.safe_load((wf / "ci.yml").read_text(encoding="utf-8"))


def test_main_has_one_group_and_only_a_pull_request_cancels() -> None:
    concurrency = _ci().get("concurrency")
    assert concurrency == {"group": GROUP, "cancel-in-progress": CANCEL}, concurrency


def test_ci_runs_on_the_events_the_group_was_decided_for() -> None:
    on = _ci().get("on", _ci().get(True))
    # BOUNDED, not equality. `merge_group` (which #659 adds) is the one extra
    # trigger allowed: each queue entry has a ref of its own, so a group of its
    # own, and it never cancels. Others would land in a group they were not
    # decided for: `pull_request_target`, `schedule` and `workflow_dispatch` on
    # main all carry main's ref, so they would queue behind main's run and could
    # replace main's pending run (review of 7c9d2535, restated for this group).
    assert {"push", "pull_request"} <= set(on) <= {"push", "pull_request", "merge_group"}, on
    assert on["push"] == {"branches": ["main"]}, on["push"]

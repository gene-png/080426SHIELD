"""CI on `main` is never cancelled by the next merge; a PR's superseded run is.

`ci.yml` grouped every run by `github.ref` with `cancel-in-progress: true`. On a
pull request that is right: a new push makes the old run worthless. On `main`
it is wrong: each merge is a different tree, and merging the next PR cancelled
the run testing the previous one, so main's own CI never finished: the main
runs for 7b396488, 779bba01, 1ab60b79, 25b34592 and 9b5623ba (2026-10-16) all
ended `cancelled`, and the combination of those merges went untested on main.

The group for a push is therefore the commit, which no other run shares; for a
pull request it stays the ref. Pinned by equality: the expression IS the
behaviour, and GitHub evaluates it, not this file.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from tests._paths import find_workflows_dir

pytestmark = pytest.mark.unit

#: Only a pull request cancels a run in progress; a push never does.
CANCEL = "${{ github.event_name == 'pull_request' }}"
GROUP = (
    "${{ github.workflow }}-${{ github.event_name == 'pull_request' && github.ref || github.sha }}"
)


def _ci() -> dict:
    wf = find_workflows_dir(pathlib.Path(__file__).resolve())
    if wf is None:
        # The api container mounts only apps/api. On a full checkout (CI) this
        # cannot fire: ci.yml's "the audit-gate tests must not skip on a full
        # checkout" step fails if find_workflows_dir returns None there.
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    return yaml.safe_load((wf / "ci.yml").read_text(encoding="utf-8"))


def test_a_push_to_main_has_a_group_of_its_own() -> None:
    concurrency = _ci().get("concurrency")
    assert concurrency == {"group": GROUP, "cancel-in-progress": CANCEL}, concurrency


def test_ci_runs_on_both_events_the_group_tells_apart() -> None:
    # The group's two arms are only meaningful while CI runs on both events.
    on = _ci().get("on", _ci().get(True))
    # BOUNDED, not equality: `merge_group` (which #659 adds) is the one extra
    # trigger allowed, because each queue entry is its own temporary commit, so
    # the commit arm gives it a group of its own. Others are NOT safe there:
    # `pull_request_target`'s sha is the base tip (every PR would share one
    # group), and `schedule` / `workflow_dispatch` on main would share a push's
    # group. Sharing a group serialises runs, and a newer PENDING run replaces
    # an older pending one even without cancel-in-progress (review of 7c9d2535).
    assert {"push", "pull_request"} <= set(on) <= {"push", "pull_request", "merge_group"}, on
    assert on["push"] == {"branches": ["main"]}, on["push"]

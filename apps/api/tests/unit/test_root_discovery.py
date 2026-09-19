"""Both directions of the two root searches that replaced `parents[N]` (#314).

`CLAUDE.md`: *a guard must be observed in BOTH states before it is trusted.
Watching it fire proves it fires; it does not prove it passes.*

The first version of #314's fix was observed only in the state that fires.
Nothing asserted that `find_workflows_dir` RETURNS something on a real
checkout, so a typo in the marker path — `audit_gate.yml`, `.gihub` — would
have skipped the audit-gate module on the host and on the CI runner alike,
forever, exit 0. `check_test_integrity.py` does not look at skips and
`check_gate_fixtures.py` covers gates rather than tests, so nothing else in the
repo could have noticed.

`check_recalled_counts.root_from` is the sibling these follow: split out so it
can be tested without moving files, and pinned in both directions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests._paths import find_workflows_dir

pytestmark = pytest.mark.unit


def _checkout(tmp_path: Path) -> Path:
    """A tmp tree shaped like a checkout, down to this file's own depth."""
    here = tmp_path / "apps" / "api" / "tests" / "unit"
    here.mkdir(parents=True)
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    return here


def test_the_workflows_directory_is_found_from_a_checkout(tmp_path: Path) -> None:
    """THE PASSING STATE, and the one the first version never observed."""
    here = _checkout(tmp_path)
    assert find_workflows_dir(here / "test_x.py") == tmp_path / ".github" / "workflows"


def test_it_is_found_even_when_the_workflow_FILE_is_absent(tmp_path: Path) -> None:
    """The discriminator, stated as its own test because it is the whole fix.

    A checkout whose `audit-gate.yml` was renamed or folded into another
    workflow still HAS the directory. That must stay distinguishable from the
    container, where there is no `.github/` at all — otherwise deleting the
    workflow silently retires the test that guards it.
    """
    here = _checkout(tmp_path)
    found = find_workflows_dir(here / "test_x.py")
    assert found is not None, (
        "an empty .github/workflows must still be FOUND; keying on the "
        "workflow file collapses 'renamed' into 'I am in the container'"
    )
    assert not (found / "audit-gate.yml").exists()


def test_no_github_anywhere_returns_None(tmp_path: Path) -> None:
    """THE FIRING STATE. This is the api container, and nothing else.

    The api service mounts only `./apps/api` and `./pyproject.toml`, so no
    ancestor of `/app/tests/unit/` holds `.github`.
    """
    here = tmp_path / "app" / "tests" / "unit"
    here.mkdir(parents=True)
    assert find_workflows_dir(here / "test_x.py") is None


def test_the_nearest_directory_wins(tmp_path: Path) -> None:
    """A checkout nested inside another must resolve to its OWN root.

    Without this the search could reach a foreign repo's workflows and return a
    wrong-but-plausible PASS, which is worse than the skip it replaced.
    """
    outer = tmp_path / ".github" / "workflows"
    outer.mkdir(parents=True)
    inner_root = tmp_path / "vendored"
    (inner_root / ".github" / "workflows").mkdir(parents=True)
    here = inner_root / "apps" / "api" / "tests" / "unit"
    here.mkdir(parents=True)
    assert find_workflows_dir(here / "test_x.py") == inner_root / ".github" / "workflows"


def test_the_workspace_search_raises_rather_than_guessing(tmp_path: Path) -> None:
    """`scripts/_common.py`'s half, and it RAISES where the other skips.

    Different consequence, different branch: a loader that silently picked a
    different root would look for seed data in the wrong place and report
    success over whatever it found. A test whose artifact is unreachable should
    not take 7000 unrelated tests down with it.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts._common import _find_workspace

    with pytest.raises(RuntimeError, match="packages"):
        _find_workspace(tmp_path / "nowhere" / "scripts" / "_common.py")


def test_the_workspace_search_finds_a_packages_directory(tmp_path: Path) -> None:
    """THE PASSING STATE for the same function.

    Both container and host shapes, because the whole point of #314 is that one
    of them used to raise `IndexError` at import.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts._common import _find_workspace

    # host shape: <repo>/apps/api/scripts/_common.py
    (tmp_path / "packages").mkdir()
    host = tmp_path / "apps" / "api" / "scripts"
    host.mkdir(parents=True)
    assert _find_workspace(host / "_common.py") == tmp_path

    # container shape: /app/scripts/_common.py with /packages beside it
    container = tmp_path / "container"
    (container / "packages").mkdir(parents=True)
    app = container / "app" / "scripts"
    app.mkdir(parents=True)
    assert _find_workspace(app / "_common.py") == container

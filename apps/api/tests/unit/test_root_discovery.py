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


def test_the_workspace_search_returns_the_NEAREST_packages_or_raises(
    tmp_path: Path,
) -> None:
    """The invariant, stated so it holds in both worlds rather than one.

    An earlier version asserted a bare `pytest.raises` from a path under
    `tmp_path`, and it FAILED IN THE CONTAINER -- `DID NOT RAISE`. The walk
    goes all the way to `/`, and `/packages` EXISTS there, because compose
    mounts `./packages/zt-data:/packages/zt-data` and Docker creates the parent.

    That is the branch's own reasoning walked into: the same `/packages`
    is why `extract_csf_questionnaires.py` searches for `reference-docs/`
    instead, written three files away in this same commit. And the green was
    the worst kind -- a GitHub runner has no `/packages` and a Windows host has
    no `packages` beside the drive root, so CI and the host both passed. The only world that
    failed was the only world #314 is about.

    So the assertion is the INVARIANT and not one of its outcomes: the search
    returns the nearest ancestor holding `packages/`, and raises when there is
    none. Which branch a given machine takes is an environment fact, and the
    test says which one it took rather than assuming.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts._common import _find_workspace

    start = tmp_path / "nowhere" / "scripts" / "_common.py"
    expected = next(
        (c for c in start.parents if (c / "packages").is_dir()),
        None,
    )
    if expected is None:
        with pytest.raises(RuntimeError, match="packages"):
            _find_workspace(start)
    else:
        assert _find_workspace(start) == expected, (
            "an ancestor holds `packages/`, so the search must return the "
            "NEAREST one rather than wandering past it"
        )


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

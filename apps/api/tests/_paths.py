"""Root discovery for tests, split out so it can be tested in BOTH states.

`CLAUDE.md`: *a guard must be observed in BOTH states before it is trusted.
Watching it fire proves it fires; it does not prove it passes.*

The first version of this lived at module scope in
`test_audit_gate_collects_only_this_branch.py` and read `__file__` directly,
which made its passing state untestable: a typo in the marker path would have
returned `None` on the host and on the CI runner alike, skipping the module
everywhere, forever, green. `check_test_integrity.py` does not look at skips,
so nothing else would have caught it.

Taking a `start` makes both directions assertable from a tmp tree, which is
what `test_root_discovery.py` does. `check_recalled_counts.root_from` is the
sibling this follows — it is split out for exactly the same reason and is
pinned in both directions.
"""

from __future__ import annotations

from pathlib import Path


def find_workflows_dir(start: Path) -> Path | None:
    """The nearest `.github/workflows` DIRECTORY at or above `start`.

    The directory and not a FILE inside it, and that is the whole point: a
    checkout that has the directory and not the file is a real state that must
    fail loudly, while no `.github/` anywhere means the api container, where
    only `./apps/api` is mounted. Keying on a file collapses those two.
    """
    for candidate in [start, *start.parents]:
        if (candidate / ".github" / "workflows").is_dir():
            return candidate / ".github" / "workflows"
    return None

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


#: Where `docker-compose.yml` mounts the web bundle's target constants in the
#: api container, read-only (#422). A CI checkout has the file in place instead.
WEB_PARITY_TARGETS = Path("/web-parity/assessment-targets.ts")


def find_web_assessment_targets(
    start: Path, container_path: Path = WEB_PARITY_TARGETS
) -> Path | None:
    """`apps/web/src/lib/assessment-targets.ts` from a checkout at or above
    `start`, else the api container's read-only mount, else None.

    Mounted at `/web-parity/` and NOT under `/apps/...`: the zt-data mount
    already made `/packages` exist in the container, and `test_root_discovery.py`
    records what that did to a walk-up search keyed on `packages/`. A `/apps`
    would set the same trap for anything keyed on `apps/`.
    """
    for candidate in [start, *start.parents]:
        ts = candidate / "apps" / "web" / "src" / "lib" / "assessment-targets.ts"
        if ts.is_file():
            return ts
    return container_path if container_path.is_file() else None


#: Where `docker-compose.yml` mounts the ZT catalogs' source documents in the
#: api container, read-only (#838): `reference-docs/<name>` -> `/zt-sources/<name>`.
#: NOT at `/reference-docs`: `extract_csf_questionnaires.py` finds a checkout by
#: walking up for `reference-docs/`, and a root-level mount would make `/` one
#: (the `/packages` trap `test_root_discovery.py` records).
ZT_SOURCES = Path("/zt-sources")


def find_zt_source(start: Path, name: str, container_root: Path = ZT_SOURCES) -> Path | None:
    """`reference-docs/<name>` from a checkout at or above `start`, else the api
    container's read-only mount `/zt-sources/<name>`, else None."""
    for candidate in [start, *start.parents]:
        directory = candidate / "reference-docs" / name
        if directory.is_dir():
            return directory
    mounted = container_root / name
    return mounted if mounted.is_dir() else None

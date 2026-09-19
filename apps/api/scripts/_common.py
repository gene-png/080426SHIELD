"""Shared helpers for seed loaders.

Loaders are idempotent — they upsert by primary key (or natural key) so
re-running them is safe.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _find_workspace(start: Path | None = None) -> Path:
    """The directory holding `packages/`, found by SEARCHING UPWARD.

    This was `parents[3]`, correct for the host checkout
    (`apps/api/scripts/_common.py` puts the repo root three up) and an
    `IndexError` inside the api container, which mounts `./apps/api` at `/app`
    and `./packages/zt-data` at `/packages/zt-data` -- so this file has three
    parents in total and the workspace is `/`, not `parents[3]`.

    At module scope that is an import-time crash, so
    `load_zt_questionnaires.py` and `load_csf_tier_questionnaires.py` -- the
    two importers of this module -- could not even IMPORT in the container
    (#314). Fixing the import does not make both of them work there, and the
    difference is worth stating rather than implying: compose mounts only
    `./packages/zt-data`, so in the container `WORKSPACE` is `/` and
    `PACKAGES` is a partial shadow holding one of the repo's three packages.
    `load_zt_questionnaires` genuinely runs there now.
    `load_csf_tier_questionnaires` gets past import and then fails on
    `FileNotFoundError: /packages/csf-data/source/...`, which is loud and names
    a missing file rather than a missing mount -- strictly better than the
    `IndexError` it replaces, and still not "it works".

    "Workspace" is also the generous name for `/`. It is the directory holding
    `packages/`, which is what this searches for and all it claims. `seed_demo.py` is unaffected: it imports `app.models._common`,
    which is a different module with a similar name.

    Takes an optional `start` so BOTH directions are testable from a tmp tree
    -- `test_root_discovery.py` pins the raise AND the find. A guard observed
    only in the state that fires is not trusted; `check_recalled_counts.root_from`
    is split out for the same reason.

    Raises rather than guessing when no candidate has a `packages/` directory.
    A loader that silently picked a different root would look up seed data in
    the wrong place and report success over whatever it found -- the failure
    this file's own callers exist to avoid.
    """
    here = (start or Path(__file__)).resolve()
    for candidate in here.parents:
        if (candidate / "packages").is_dir():
            return candidate
    raise RuntimeError(
        f"cannot locate a workspace with a `packages/` directory above {here}. "
        "On the host that is the repo root; in the api container it is `/`, "
        "where docker-compose mounts `./packages/zt-data`."
    )


WORKSPACE = _find_workspace()
PACKAGES = WORKSPACE / "packages"


def print_progress(loader: str, message: str) -> None:
    print(f"[seed:{loader}] {message}", flush=True)


def die(loader: str, message: str, *, exit_code: int = 1) -> None:
    print(f"[seed:{loader}] ERROR: {message}", file=sys.stderr, flush=True)
    raise SystemExit(exit_code)

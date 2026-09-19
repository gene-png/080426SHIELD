"""Shared helpers for seed loaders.

Loaders are idempotent — they upsert by primary key (or natural key) so
re-running them is safe.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _find_workspace() -> Path:
    """The directory holding `packages/`, found by SEARCHING UPWARD.

    This was `parents[3]`, correct for the host checkout
    (`apps/api/scripts/_common.py` puts the repo root three up) and an
    `IndexError` inside the api container, which mounts `./apps/api` at `/app`
    and `./packages/zt-data` at `/packages/zt-data` -- so this file has three
    parents in total and the workspace is `/`, not `parents[3]`.

    At module scope that is an import-time crash, so
    `load_zt_questionnaires.py` and `load_csf_tier_questionnaires.py` -- the
    two importers of this module -- could not run in the container at all
    (#314). `seed_demo.py` is unaffected: it imports `app.models._common`,
    which is a different module with a similar name.

    Raises rather than guessing when no candidate has a `packages/` directory.
    A loader that silently picked a different root would look up seed data in
    the wrong place and report success over whatever it found -- the failure
    this file's own callers exist to avoid.
    """
    here = Path(__file__).resolve()
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

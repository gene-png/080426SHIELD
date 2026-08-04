"""Shared helpers for seed loaders.

Loaders are idempotent — they upsert by primary key (or natural key) so
re-running them is safe.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Resolve the workspace root from this file:
# apps/api/scripts/_common.py -> <repo root>.
WORKSPACE = Path(__file__).resolve().parents[3]
PACKAGES = WORKSPACE / "packages"


def print_progress(loader: str, message: str) -> None:
    print(f"[seed:{loader}] {message}", flush=True)


def die(loader: str, message: str, *, exit_code: int = 1) -> None:
    print(f"[seed:{loader}] ERROR: {message}", file=sys.stderr, flush=True)
    raise SystemExit(exit_code)

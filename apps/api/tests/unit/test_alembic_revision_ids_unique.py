"""Every migration file is a revision Alembic walks: no id is declared twice (#723).

`test_alembic_single_head.py` builds a SET of the revisions Alembic walked, so
it cannot SEE a repeated id, and #723 was filed on the suspicion that a
duplicate would be dropped with every gate green. Measured 2026-09-26 on the
installed Alembic, that is not what happens: a second file declaring 0055
(chained from 0054), 0056 (the head) or 0030 (mid-chain) each turned both
single-head tests red too, through the heads/overlap errors the duplicate
causes. So this is a RATCHET, not the only guard: it names the duplicate and
the two files outright rather than reporting a fork, and it does not depend on
how a future Alembic resolves the collision. Parallel branches pick their
numbers from `main` and renumber at landing, so two files claiming one id is
one missed rename away; #640 was in exactly that state until its rename.

Two independent readings, so neither can agree with Alembic by construction:
the FILES on disk, and the ids those files DECLARE (read from their text).
"""

from __future__ import annotations

import re
import warnings
from collections import Counter
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

API_ROOT = Path(__file__).resolve().parents[2]
VERSIONS = API_ROOT / "alembic" / "versions"
# The module-level assignment, annotated or not: `revision: str = "0055"`.
_DECLARED = re.compile(r'^revision(?:\s*:\s*str)?\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def _migration_files() -> list[Path]:
    files = sorted(p for p in VERSIONS.glob("*.py") if not p.name.startswith("__"))
    # Asserted first: an empty or wrong directory would make every count agree.
    assert len(files) > 50, f"found {len(files)} migration files in {VERSIONS}: wrong directory?"
    return files


def _walked() -> list[str]:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    with warnings.catch_warnings():
        # Alembic only WARNS on a duplicate id; the assertions below are the
        # refusal, so the warning is not what this test relies on.
        warnings.simplefilter("ignore")
        return [rev.revision for rev in ScriptDirectory.from_config(cfg).walk_revisions()]


@pytest.mark.unit
def test_no_two_migration_files_declare_the_same_revision_id() -> None:
    declared: dict[str, list[str]] = {}
    for path in _migration_files():
        ids = _DECLARED.findall(path.read_text(encoding="utf-8"))
        assert len(ids) == 1, f"{path.name}: expected one `revision = ...` line, found {ids}"
        declared.setdefault(ids[0], []).append(path.name)
    repeated = {rev: names for rev, names in declared.items() if len(names) > 1}
    assert not repeated, f"revision ids declared by more than one file: {repeated}"


@pytest.mark.unit
def test_alembic_walks_one_revision_per_migration_file() -> None:
    files = _migration_files()
    walked = _walked()
    twice = sorted(rev for rev, n in Counter(walked).items() if n > 1)
    assert not twice, f"Alembic walked these revisions more than once: {twice}"
    assert len(walked) == len(files), (
        f"{len(files)} migration files but Alembic walked {len(walked)} revisions: "
        "a file whose id another file also declares is silently dropped"
    )

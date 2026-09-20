"""Test fixtures."""

from __future__ import annotations

import os
from typing import Any

import pytest

# Keep tests fully offline: no DB, no Redis, no LLM. Routes that need those
# will set up their own ephemeral resources in later stages.
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SHIELD_LLM_MODE", "fixture")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


# Keep pytest out of the gate fixtures: they are INPUTS, not tests.
#
# `testpaths = ["tests"]`, so a bare `pytest` from apps/api walks tests/gates.
# Two fixtures are named `test_*.py` because the gate they exercise
# (`check_test_integrity`) only looks at that pattern -- renaming them would make
# them invisible to the thing they test. One imports a symbol that does not
# exist, deliberately: it is a verbatim reproduction of the #72 instance, kept so
# `check_gate_fixtures.py` can assert the gate exits 1 on it. Collecting them
# fails for a reason unrelated to whatever the developer was doing.
#
# This lives HERE rather than in tests/gates/conftest.py because that directory
# is excluded from ruff and black -- a conftest there is real code going unlinted,
# which is an exclusion wider than its own justification ("files that are data").
#
# LOAD-BEARING ON THE HARNESS RUNNING, like the ruff/black/prettier/test-integrity
# exclusions: if the "gates can fail" step goes away, this goes with it.
#
# CI is unaffected either way -- it runs `pytest -m unit tests/unit`.
collect_ignore_glob = ["gates/*"]


@pytest.fixture
def xlsx_data_start():
    """Where a playbook worksheet's data begins, DERIVED rather than counted.

    Five tests hardcoded "headings on row 1, data from row 2". That was true
    until #294 put the approval banner above the headings, and then every one
    of them failed at once -- which is the good outcome, and the reason they
    are not simply renumbered to 2 and 3: a transcribed index is correct for
    one layout and silently wrong for the next.

    The freeze pane is the renderer's OWN statement of where the frozen header
    block ends, set in `playbook_export._header` from the row `append` actually
    wrote. So the two sides of any assertion built on this can only agree if
    the sheet is laid out the way the renderer intends -- the property
    `CLAUDE.md` asks for, and the reason this reads `freeze_panes` rather than
    searching for a row that looks like a header.

    It does NOT pin the banner's existence. Drop the banner and this returns 2
    and those tests still pass, correctly: they are about the Action Plan's
    columns, not about #294. `test_every_data_sheet_freezes_its_banner` is
    what goes red there.
    """

    def _start(ws: Any) -> int:
        frozen = ws.freeze_panes
        assert frozen, (
            f"sheet {ws.title!r} has no freeze pane, so there is nothing to "
            f"derive the layout from. Either the sheet is not one of the "
            f"`_header`-built data sheets, or `_header` stopped freezing."
        )
        digits = "".join(ch for ch in str(frozen) if ch.isdigit())
        assert digits, f"cannot read a row out of freeze_panes={frozen!r}"
        row = int(digits)
        assert row >= 2, (
            f"sheet {ws.title!r} freezes at row {row}, which leaves no header "
            f"row above the data"
        )
        return row

    return _start

"""Migration 0076 (#982, number assigned at #736 6217663777): a nullable
`zt_answers.target_source`, with no default and no backfill.

NULL means "origin not recorded": every per-capability target stored before
this migration may have been set by an earlier AI run (before #981), and
nothing can tell, so none is presented as consultant-chosen (missing data
defaults to unconfirmed). The downgrade drops the column; a re-upgrade gives
NULL back, which is the honest reading of a fact that was lost.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

pytestmark = pytest.mark.unit

API_ROOT = Path(__file__).resolve().parents[2]


def _cfg(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _columns(engine: sa.Engine) -> dict[str, dict]:
    return {c["name"]: c for c in sa.inspect(engine).get_columns("zt_answers")}


def test_0076_adds_target_source_nullable_with_no_default_and_drops_it(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'db.sqlite'}"
    cfg = _cfg(url)
    command.upgrade(cfg, "0076")
    engine = sa.create_engine(url, future=True)
    col = _columns(engine)["target_source"]
    assert col["nullable"] is True
    assert col["default"] is None, "an unrecorded origin must read NULL, never a guess"

    command.downgrade(cfg, "-1")

    assert "target_source" not in _columns(sa.create_engine(url, future=True))

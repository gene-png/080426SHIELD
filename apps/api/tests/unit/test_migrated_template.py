"""The migrate-once template (`tests/_migrated_template.py`) hands a test the
same database a real upgrade would, and only for the one call shape it owns.

Every expected value here comes from Alembic itself -- a real upgrade into a
second file -- never from the module under test.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

pytestmark = pytest.mark.unit

_API_ROOT = Path(__file__).resolve().parents[2]
_MODULE = "tests._migrated_template"


def _installed():
    """The module as `tests/conftest.py` installed it. Looked up, never imported
    here, so deleting the conftest line leaves this None and the tests red."""
    return sys.modules.get(_MODULE)


def _cfg(path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    url = f"sqlite:///{path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config(str(_API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _clauses(sql: str | None) -> tuple[str, ...]:
    """A CREATE statement as its sorted clauses. Two real upgrades of this chain
    emit a rebuilt table's constraints in different orders (batch mode rebuilds
    from a set), so the statement text is not stable; the set of clauses is, and
    it still shows any column or constraint added, dropped or changed."""
    lines = (line.strip().rstrip(",").strip() for line in (sql or "").splitlines())
    return tuple(sorted(line for line in lines if line))


def _snapshot(path: Path) -> dict:
    """Schema, version and every table's row count: what a test can observe."""
    con = sqlite3.connect(path)
    try:
        schema = sorted(
            (kind, name, table, _clauses(sql))
            for kind, name, table, sql in con.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        # Table names come from sqlite_master of a database this test built.
        count_sql = 'SELECT COUNT(*) FROM "{}"'
        counts = {t: con.execute(count_sql.format(t)).fetchone()[0] for t in tables}
        version = [r[0] for r in con.execute("SELECT version_num FROM alembic_version")]
    finally:
        con.close()
    return {"schema": schema, "rows": counts, "version": version}


def test_conftest_installs_it() -> None:
    mod = _installed()
    assert mod is not None, "tests/conftest.py no longer imports tests._migrated_template"
    assert command.upgrade is mod.upgrade


def test_a_fresh_upgrade_to_head_is_a_copy_identical_to_a_real_upgrade(
    tmp_path, monkeypatch
) -> None:
    mod = _installed()
    assert mod is not None
    served_before = mod.stats["served"]

    copied = tmp_path / "copied.db"
    command.upgrade(_cfg(copied, monkeypatch), "head")

    real = tmp_path / "real.db"
    mod._real_upgrade(_cfg(real, monkeypatch), "head")

    # The positive state first: it was served from the template.
    assert mod.stats["served"] == served_before + 1
    expected = _snapshot(real)
    assert expected["version"] and expected["schema"]
    assert _snapshot(copied) == expected


def test_a_stale_template_is_an_error_not_an_older_schema(tmp_path, monkeypatch) -> None:
    mod = _installed()
    assert mod is not None
    command.upgrade(_cfg(tmp_path / "warm.db", monkeypatch), "head")  # the template exists
    monkeypatch.setattr(mod, "_head", "0000_not_the_head")
    with pytest.raises(RuntimeError, match=r"is at \['\w+'\], not head '0000_not_the_head'"):
        command.upgrade(_cfg(tmp_path / "stale.db", monkeypatch), "head")


def test_a_named_revision_migrates_for_real(tmp_path, monkeypatch) -> None:
    mod = _installed()
    assert mod is not None
    served_before, real_before = mod.stats["served"], mod.stats["real"]
    path = tmp_path / "older.db"
    command.upgrade(_cfg(path, monkeypatch), "0065")
    assert _snapshot(path)["version"] == ["0065"]
    assert (mod.stats["served"], mod.stats["real"]) == (served_before, real_before + 1)


def test_an_existing_file_is_upgraded_for_real(tmp_path, monkeypatch) -> None:
    mod = _installed()
    assert mod is not None
    path = tmp_path / "stepwise.db"
    cfg = _cfg(path, monkeypatch)
    command.upgrade(cfg, "0065")
    served_before = mod.stats["served"]
    command.upgrade(cfg, "head")
    assert mod.stats["served"] == served_before
    real = tmp_path / "real.db"
    mod._real_upgrade(_cfg(real, monkeypatch), "head")
    assert _snapshot(path)["version"] == _snapshot(real)["version"]


def test_the_opt_out_migrates_for_real(tmp_path, monkeypatch) -> None:
    mod = _installed()
    assert mod is not None
    monkeypatch.setenv(mod.OPT_OUT_ENV, "1")
    served_before, real_before = mod.stats["served"], mod.stats["real"]
    command.upgrade(_cfg(tmp_path / "optout.db", monkeypatch), "head")
    assert (mod.stats["served"], mod.stats["real"]) == (served_before, real_before + 1)

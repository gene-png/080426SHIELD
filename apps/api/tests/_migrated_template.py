"""Migrate once per test process, copy per test.

WHY. About a fifth of the unit tests build a fresh SQLite database through
`command.upgrade(cfg, "head")`, and each such call ran every migration: 57% of
the suite's time on GitHub's runners, about 1.3 s per call (bench run
38802579958, #736 6202689246). The schema at head is the same every time, so it
is built once, by the real migrations, and copied.

WHAT IS INTERCEPTED. Exactly one shape: `upgrade(cfg, "head")`, no other
arguments, where the config names a `sqlite:///<path>` file that does not exist
yet -- a fresh fixture database. Everything else goes to Alembic untouched: a
named revision, a downgrade, a file that already exists (a test that migrated to
an older revision and is now upgrading the rest of the way), an in-memory URL, a
non-SQLite URL, or no URL at all.

WHY IT CANNOT HAND A TEST A WRONG DATABASE. The template is built by the real
`command.upgrade(cfg, "head")`, so every test process still runs the full chain
from empty to head once. The head revision is read once from the script
directory, and each copy's `alembic_version` must equal it or the call raises,
so a stale template is an error, never a quietly older schema.
`test_migrated_template.py` pins the copy as schema-identical to a real upgrade.

TURNING IT OFF. `SHIELD_TEST_REAL_MIGRATIONS=1` runs every upgrade for real, as
before. Use it to time the old path or to rule this module out of a failure.

Installed by `tests/conftest.py` importing this module, before any test module
imports `alembic.command`. Tests call `command.upgrade` as an attribute, so the
replacement reaches every call site.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile

import structlog
from alembic import command

_log = structlog.get_logger(__name__)

OPT_OUT_ENV = "SHIELD_TEST_REAL_MIGRATIONS"

_real_upgrade = command.upgrade
_template_path: str | None = None
_head: str | None = None
#: Counts for the tests and for anyone timing a run. `served` copies, `real` runs.
stats = {"served": 0, "real": 0}


def _fresh_sqlite_file(cfg) -> str | None:
    """The file path when `cfg` names a SQLite file that does not exist yet."""
    url = cfg.get_main_option("sqlalchemy.url") or ""
    if not url.startswith("sqlite:///"):
        return None
    path = url[len("sqlite:///") :]
    if not path or path == ":memory:" or os.path.exists(path):
        return None
    return path


def _build_template(cfg) -> str:
    """Run the real migrations once, into a private file, and remember the head."""
    global _template_path, _head
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(cfg).get_current_head()
    path = os.path.join(tempfile.mkdtemp(prefix="shield-migrated-"), "template.db")
    url = f"sqlite:///{path}"
    old_url = cfg.get_main_option("sqlalchemy.url")
    old_env = os.environ.get("DATABASE_URL")
    try:
        cfg.set_main_option("sqlalchemy.url", url)
        os.environ["DATABASE_URL"] = url
        _real_upgrade(cfg, "head")
    finally:
        cfg.set_main_option("sqlalchemy.url", old_url)
        if old_env is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_env
    _template_path, _head = path, head
    _log.info("tests.migrated_template.built", head=head, path=path)
    return path


def _version_of(path: str) -> list[str]:
    con = sqlite3.connect(path)
    try:
        return [row[0] for row in con.execute("SELECT version_num FROM alembic_version")]
    finally:
        con.close()


def upgrade(cfg, revision, *args, **kwargs):
    """`alembic.command.upgrade`, serving a fresh-file upgrade to head by copy."""
    if os.environ.get(OPT_OUT_ENV) == "1" or revision != "head" or args or kwargs:
        stats["real"] += 1
        return _real_upgrade(cfg, revision, *args, **kwargs)
    path = _fresh_sqlite_file(cfg)
    if path is None:
        stats["real"] += 1
        return _real_upgrade(cfg, revision)
    template = _template_path or _build_template(cfg)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    shutil.copyfile(template, path)
    found = _version_of(path)
    if found != [_head]:
        raise RuntimeError(
            f"migrated template: the copy at {path} is at {found}, not head {_head!r}; "
            f"set {OPT_OUT_ENV}=1 to migrate for real"
        )
    stats["served"] += 1
    return None


command.upgrade = upgrade

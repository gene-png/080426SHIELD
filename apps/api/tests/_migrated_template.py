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
from empty to head once. Templates are kept per script directory, and each
copy's `alembic_version` must equal its caller's head or the call raises. Today
every caller names the same `apps/api/alembic`, so the check cannot fire on a
reachable state: it is a ratchet against a caller that points at another chain,
or a template file replaced underneath the process, and a test forces it.
`test_migrated_template.py` pins the copy as schema-identical to a real upgrade.

TURNING IT OFF. `SHIELD_TEST_REAL_MIGRATIONS=1` runs every upgrade for real, as
before. Use it to time the old path or to rule this module out of a failure.

ENVIRONMENT. The template is built with the first caller's environment. That
is safe only while no migration reads one: today none imports `app` or reads
`os.environ` (`grep -E "os.environ|getenv|from app" alembic/versions/*.py` is
empty), and `alembic/env.py` reads settings only when the config names no URL,
which this module always sets. A migration that starts reading the environment
makes this module wrong; turn it off with the opt-out until it is reworked.

Installed by `tests/conftest.py` importing this module, before any test module
imports `alembic.command`. Tests call `command.upgrade` as an attribute, so the
replacement reaches every call site.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sqlite3
import sys
import tempfile

import structlog
from alembic import command

_log = structlog.get_logger(__name__)

OPT_OUT_ENV = "SHIELD_TEST_REAL_MIGRATIONS"

_real_upgrade = command.upgrade
#: script_location -> (template path, head revision). Keyed on the caller's
#: script directory, so a caller pointing at a different chain gets its own
#: template, and the version check compares each copy with ITS caller's head.
_templates: dict[str, tuple[str, str]] = {}
#: Counts for the tests and for anyone timing a run. `served` copies, `real` runs.
stats = {"served": 0, "real": 0}


def _fresh_sqlite_file(cfg) -> str | None:
    """The file path when `cfg` names a SQLite file that does not exist yet."""
    url = cfg.get_main_option("sqlalchemy.url") or ""
    if not url.startswith("sqlite:///"):
        return None
    path = url[len("sqlite:///") :]
    # A query string or a missing directory is not the plain fixture shape:
    # Alembic decides those, as it did before this module.
    if not path or path == ":memory:" or "?" in path or os.path.exists(path):
        return None
    if not os.path.isdir(os.path.dirname(path) or "."):
        return None
    return path


def _script_location(cfg) -> str:
    return os.path.realpath(cfg.get_main_option("script_location") or "")


def _head_of(cfg) -> str:
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(cfg).get_current_head()


def _build_template(cfg) -> tuple[str, str]:
    """Run the real migrations once per script directory, into a private file."""
    head = _head_of(cfg)
    path = os.path.join(tempfile.mkdtemp(prefix="shield-migrated-"), "template.db")
    url = f"sqlite:///{path}"
    old_url = cfg.get_main_option("sqlalchemy.url")
    old_env = os.environ.get("DATABASE_URL")
    try:
        cfg.set_main_option("sqlalchemy.url", url)
        os.environ["DATABASE_URL"] = url
        _real_upgrade(cfg, "head")
        stats["real"] += 1
    finally:
        cfg.set_main_option("sqlalchemy.url", old_url)
        if old_env is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_env
    _templates[_script_location(cfg)] = (path, head)
    _log.info("tests.migrated_template.built", head=head, path=path)
    return path, head


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
    template, head = _templates.get(_script_location(cfg)) or _build_template(cfg)
    shutil.copyfile(template, path)
    found = _version_of(path)
    if found != [head]:
        raise RuntimeError(
            f"migrated template: the copy at {path} is at {found}, not head {head!r}; "
            f"set {OPT_OUT_ENV}=1 to migrate for real"
        )
    stats["served"] += 1
    return None


command.upgrade = upgrade


@atexit.register
def _report() -> None:
    """One line per test process, so a reader can see which path ran (core
    principle 5). On stderr at exit: pytest's capture has ended by then."""
    for path, _ in _templates.values():
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)
    nl = chr(10)
    sys.stderr.write(
        f"tests.migrated_template: served {stats['served']} fresh databases from the "
        f"template and ran {stats['real']} upgrades for real "
        f"({OPT_OUT_ENV}={os.environ.get(OPT_OUT_ENV, 'unset')}){nl}"
    )

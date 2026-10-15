"""Benchmark-only pytest plugin: a migrated SQLite TEMPLATE instead of 71
migrations per test. Not for merge; it measures what the change would save.

Loaded with `-p template_db`. It patches `alembic.command.upgrade` at IMPORT
time, so `ci_timing` (which wraps at configure) measures the patched call.

The ONLY call it intercepts is `upgrade(cfg, "head")` whose config names a
`sqlite:///<path>` file that does not exist yet -- a fresh fixture database.
For that call it copies a template built once per process (by the real
upgrade, into a private directory) to `<path>`, and THEN runs the real
`upgrade(cfg, "head")` on the copy. Alembic reads `alembic_version`, finds the
head, and does nothing -- so Alembic itself confirms the copy is at head on
every call, and a stale or wrong template would migrate (visibly slow) rather
than pass silently. Every other call (a named revision, a downgrade, an
existing file, a non-SQLite URL, no URL) goes to the real function untouched.

Writes counts and seconds to $TEMPLATE_DB_OUT at exit.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import sqlite3
import tempfile
import time

from alembic import command

_real_upgrade = command.upgrade
_template: str | None = None
_head: str | None = None
#: "alembic" (default): run the real upgrade on the copy, a no-op Alembic itself
#: confirms. "version": read `alembic_version` from the copy and require the head
#: revision computed once from the script directory -- same guarantee, without
#: loading 71 migration modules per test. A mismatch raises either way.
_MODE = os.environ.get("TEMPLATE_DB_MODE", "alembic")
_stats = {"mode": os.environ.get("TEMPLATE_DB_MODE", "alembic"), "intercepted": 0, "passthrough": 0, "build_seconds": 0.0, "copy_seconds": 0.0,
          "noop_upgrade_seconds": 0.0, "passthrough_reasons": {}}


def _fresh_sqlite_path(cfg) -> str | None:
    url = cfg.get_main_option("sqlalchemy.url") or ""
    if not url.startswith("sqlite:///"):
        return None
    path = url[len("sqlite:///"):]
    if not path or path == ":memory:" or os.path.exists(path):
        return None
    return path


def _build_template(cfg) -> str:
    global _template, _head
    from alembic.script import ScriptDirectory

    _head = ScriptDirectory.from_config(cfg).get_current_head()
    d = tempfile.mkdtemp(prefix="shield-template-")
    path = os.path.join(d, "template.db")
    url = f"sqlite:///{path}"
    old_url = cfg.get_main_option("sqlalchemy.url")
    old_env = os.environ.get("DATABASE_URL")
    t = time.perf_counter()
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
    _stats["build_seconds"] += time.perf_counter() - t
    _template = path
    return path


def _note_passthrough(reason: str) -> None:
    _stats["passthrough"] += 1
    _stats["passthrough_reasons"][reason] = _stats["passthrough_reasons"].get(reason, 0) + 1


def upgrade(cfg, revision, *args, **kwargs):
    if revision != "head" or args or kwargs:
        _note_passthrough("not_plain_head")
        return _real_upgrade(cfg, revision, *args, **kwargs)
    path = _fresh_sqlite_path(cfg)
    if path is None:
        _note_passthrough("not_a_fresh_sqlite_file")
        return _real_upgrade(cfg, revision)
    template = _template or _build_template(cfg)
    t = time.perf_counter()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    shutil.copyfile(template, path)
    _stats["copy_seconds"] += time.perf_counter() - t
    _stats["intercepted"] += 1
    t = time.perf_counter()
    try:
        if _MODE == "version":
            con = sqlite3.connect(path)
            try:
                found = [r[0] for r in con.execute("SELECT version_num FROM alembic_version")]
            finally:
                con.close()
            if found != [_head]:
                raise RuntimeError(f"template_db: copied database is at {found}, not head {_head!r}")
            return None
        return _real_upgrade(cfg, revision)
    finally:
        _stats["noop_upgrade_seconds"] += time.perf_counter() - t


command.upgrade = upgrade


@atexit.register
def _dump() -> None:
    out = os.environ.get("TEMPLATE_DB_OUT")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(_stats, fh, indent=1)

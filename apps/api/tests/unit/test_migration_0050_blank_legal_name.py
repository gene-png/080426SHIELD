"""Migration 0050 runs against DATA, one row per whitespace class.

`grep 0050 apps/api` used to return only prose: the UPDATE had never executed
against a row in CI, and the dev database has zero blanks, so production data
could not exercise it either. **The migration was pinned by nothing.**

That mattered because its first version was one SQL statement whose predicate,
`trim(legal_name) = ''`, is SPACE-ONLY on both engines. A tab, a newline or a
non-breaking space survived it, and the migration logged
`normalised 0 blank legal_name row(s)` -- byte-identical to what a clean
database logs. There was no reading of that output that revealed the miss.

The parameters below come from the ENGINE's and the LANGUAGE's disagreement
rather than from the code under test: each is a string `str.strip()` treats as
empty, and the first is the only one single-argument SQL `trim()` also treats
as empty. That is what makes this a sweep rather than a transcript -- the cases
were derived from the measured gap, not from reading the fix.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

# Spelled with chr() rather than as escapes: an escape typed into a string
# literal in this repo has already reached a file as a REAL control byte and
# broken the parse, which is what `check_no_control_chars.py` exists to catch.
_SPACES = "   "
_TAB = chr(9)
_NEWLINE = chr(10)
_TAB_NEWLINE_SPACE = chr(9) + chr(10) + " "
_NBSP = chr(160)

#: Every one of these is empty to `str.strip()`. Only `_SPACES` is empty to
#: single-argument SQL `trim()`, measured on SQLite and Postgres 16 on
#: 2026-09-22 -- so the four below it are precisely what the SQL version missed.
#:
#: NAMED rather than derived, deliberately: these five are the cases with a
#: known engine/language disagreement behind them, and each id says which. The
#: DERIVED sweep is `test_every_whitespace_character_is_blank_to_the_migration`
#: below, which enumerates the whole Unicode whitespace class from `str.isspace`
#: so a character nobody thought of cannot escape.
BLANK_CLASSES = [
    pytest.param(_SPACES, id="spaces"),
    pytest.param(_TAB, id="tab"),
    pytest.param(_NEWLINE, id="newline"),
    pytest.param(_TAB_NEWLINE_SPACE, id="tab-newline-space"),
    pytest.param(_NBSP, id="nbsp-u00a0"),
]


def _cfg(url: str) -> Config:
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _seed_client(engine: sa.Engine, legal_name: str | None) -> uuid.UUID:
    """Insert a client row by raw SQL, at revision 0049.

    Raw SQL on purpose: this is the WORLD, not the step under test. Going
    through the app's writers would normalise the value and the test would be
    asserting against its own setup -- the shape `CLAUDE.md` records as a test
    that cannot fail.
    """
    cid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO client (id, legal_name, created_at, updated_at) "
                "VALUES (:id, :name, :now, :now)"
            ),
            {"id": str(cid), "name": legal_name, "now": "2026-09-22 00:00:00"},
        )
    return cid


def _legal_name(engine: sa.Engine, cid: uuid.UUID) -> str | None:
    with engine.begin() as conn:
        return conn.execute(
            sa.text("SELECT legal_name FROM client WHERE id = :id"), {"id": str(cid)}
        ).scalar_one()


@pytest.mark.unit
@pytest.mark.parametrize("blank", BLANK_CLASSES)
def test_0050_normalises_every_blank_class_to_null(tmp_path, blank: str) -> None:
    """A stored blank of ANY whitespace class ends the migration as NULL."""
    url = f"sqlite:///{tmp_path / 'm0050.db'}"
    command.upgrade(_cfg(url), "0049")
    engine = sa.create_engine(url, future=True)

    cid = _seed_client(engine, blank)
    # The row really is stored blank-but-not-NULL before we start; without this
    # the test could pass over an INSERT that silently did something else.
    assert _legal_name(engine, cid) == blank

    command.upgrade(_cfg(url), "0050")

    assert _legal_name(engine, cid) is None, (
        f"migration 0050 left {blank!r} stored as a name. A blank is truthy, so "
        f"it renders as an EMPTY organisation line on the client's deliverable "
        f"instead of reaching the fallback."
    )


@pytest.mark.unit
def test_0050_leaves_a_real_name_alone(tmp_path) -> None:
    """The other half of the branch, so the migration cannot pass by NULLing everything.

    Without this, `UPDATE client SET legal_name = NULL` with no WHERE clause
    satisfies every case above.
    """
    url = f"sqlite:///{tmp_path / 'm0050-keep.db'}"
    command.upgrade(_cfg(url), "0049")
    engine = sa.create_engine(url, future=True)

    kept = _seed_client(engine, "Atlas Defense Solutions")
    padded = _seed_client(engine, "  Atlas  ")

    command.upgrade(_cfg(url), "0050")

    assert _legal_name(engine, kept) == "Atlas Defense Solutions"
    # A padded REAL name is not blank, so the migration leaves it exactly as
    # stored -- trimming it here would be a second, unstated normalisation.
    # The read path strips for display; the column keeps what was written.
    assert _legal_name(engine, padded) == "  Atlas  "


@pytest.mark.unit
def test_0050_leaves_null_alone_and_reports_the_scanned_total(tmp_path, capfd) -> None:
    """A NULL row is already the target state: not touched, and NOT COUNTED.

    The first version of this test seeded one NULL row and asserted only that
    it was still NULL afterwards. That is satisfied by a migration that NULLs
    everything, by one that counts the NULL row as normalised, and by one that
    does nothing at all -- it could not fail. It was in the file added to end
    "the migration is pinned by nothing", which is the worse half.

    The counts are what discriminate, so the counts are what this asserts. The
    migration's own comment argues they are load-bearing ("'0 of 0' and
    '0 of 400' are different facts"), and nothing was reading them.

    Seeding a REAL name alongside the NULL is what makes the scanned total
    meaningful: `WHERE legal_name IS NOT NULL` must exclude the NULL row and
    include the named one, so the honest report is "0 normalised, of 1
    scanned". A migration that scanned everything would say 2.
    """
    url = f"sqlite:///{tmp_path / 'm0050-null.db'}"
    command.upgrade(_cfg(url), "0049")
    engine = sa.create_engine(url, future=True)

    already = _seed_client(engine, None)
    named = _seed_client(engine, "Atlas Defense Solutions")

    command.upgrade(_cfg(url), "0050")

    assert _legal_name(engine, already) is None
    assert _legal_name(engine, named) == "Atlas Defense Solutions"

    # `capfd`, not `caplog`, and the REASON is not the obvious one. Measured:
    # the alembic logger has NO handler of its own and DOES propagate
    # (`propagate = 1`), so propagation to root is the only reason anything
    # prints. What breaks `caplog` is that `logging.config.fileConfig` -- which
    # `alembic/env.py` calls -- REPLACES root's handlers, discarding pytest's
    # `LogCaptureHandler` part-way through the test.
    #
    # The general form is in D-082: a capture channel the system under test can
    # silently disconnect. Assert the capture is non-empty before reading it
    # (the `assert reports` below) and prefer the most primitive channel --
    # `capfd` reads the file descriptor, beneath anything logging config can
    # rearrange. This applies to any subject calling `fileConfig`,
    # `dictConfig` or `basicConfig(force=True)`, not to migrations.
    captured = capfd.readouterr()
    reports = [line for line in (captured.err + captured.out).splitlines() if "0050:" in line]
    assert reports, "migration 0050 logged no report line at all"
    assert (
        "normalised 0 blank legal_name row(s)" in reports[-1]
    ), f"0050 counted a row it did not normalise: {reports[-1]!r}"
    assert "of 1 non-NULL scanned" in reports[-1], (
        f"0050's scanned total should exclude the NULL row and include the named "
        f"one, so 1 -- got {reports[-1]!r}. '0 of 0' and '0 of 1' are different "
        f"facts and only one of them means the migration looked."
    )


@pytest.mark.unit
def test_every_whitespace_character_is_blank_to_the_migration(tmp_path) -> None:
    """The DERIVED half: the whole Unicode whitespace class, not five I picked.

    `BLANK_CLASSES` above is a named list of the five cases with a measured
    engine/language disagreement. A list is what it is, and a list cannot catch
    a character nobody thought of -- which is exactly how the SQL `trim()`
    version passed review: whoever wrote it was thinking about spaces.

    This derives the set from `str.isspace()`, the same predicate `str.strip()`
    uses, so a row holding ANY single whitespace character ends as NULL. One
    row per character, one migration run.
    """
    whitespace = [chr(cp) for cp in range(0x110000) if chr(cp).isspace()]
    assert len(whitespace) > 20, "the whitespace class collapsed; check the derivation"

    url = f"sqlite:///{tmp_path / 'm0050-all-ws.db'}"
    command.upgrade(_cfg(url), "0049")
    engine = sa.create_engine(url, future=True)

    seeded = {ch: _seed_client(engine, ch) for ch in whitespace}
    command.upgrade(_cfg(url), "0050")

    survivors = {
        f"U+{ord(ch):04X}": _legal_name(engine, cid)
        for ch, cid in seeded.items()
        if _legal_name(engine, cid) is not None
    }
    assert not survivors, (
        f"{len(survivors)} whitespace character(s) survived the migration as a stored "
        f"name: {sorted(survivors)}. Each renders as a blank organisation line."
    )

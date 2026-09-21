"""The mount check must fire on a mismatch AND pass on agreement (#gate).

A guard observed only firing is half-tested: watching it fire proves it fires,
not that it passes. A typo that halts unconditionally leaves every container
dead on arrival, and that symptom is indistinguishable from the hazard the
guard exists to catch — the api crash-loops either way.

So both states are exercised here, and so is every "could not look" branch,
because this check sits in front of `alembic upgrade head` in the api's
startup command: an exit it gets wrong stops the stack.

## The bug this file would have caught

The first draft's pattern required the revision line to carry NO annotation:

    revision = "0046"        matched
    revision: str = "0045"   did not

45 of the repo's 47 migrations use the annotated form, so it detected one
revision out of 47. A database stamped at any of the other 46 would have been
reported as a mismatch and the api would have refused to start — a gate strictly
worse than no gate. It was caught by reading the check's own output in its
FIRING state, where the exit code was right and the finding inside it was wrong.

`test_it_reads_every_revision_in_the_real_tree` is that case, pinned against the
actual migrations rather than a fixture, because the fixture would have been
written by the same person who wrote the pattern.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from check_mount_matches_database import (  # noqa: E402
    EXIT_COULD_NOT_LOOK,
    EXIT_MISMATCH,
    EXIT_OK,
    tree_revisions,
)

_VERSIONS = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions"


@pytest.mark.unit
def test_it_reads_every_revision_in_the_real_tree() -> None:
    """Against the actual migrations, not a fixture.

    A fixture here would have been written by whoever wrote the pattern and
    would have carried the same assumption about how a revision line looks.
    The repo uses two spellings and the first draft saw one of them.
    """
    files = sorted(_VERSIONS.glob("*.py"))
    revisions = tree_revisions(_VERSIONS)
    assert len(revisions) == len(files), (
        f"{len(files)} migration files yielded {len(revisions)} revisions. A "
        f"revision the pattern cannot see makes a database stamped at it look "
        f"like a mismatch, which would refuse to start the api."
    )
    # Both spellings, named, so a future migration in either form is covered.
    assert "0001" in revisions, "the annotated form `revision: str = ...` is not read"
    assert "0046" in revisions, "the bare form `revision = ...` is not read"


@pytest.mark.unit
def test_both_spellings_are_read(tmp_path: pathlib.Path) -> None:
    (tmp_path / "0001_a.py").write_text('revision: str = "0001"\n', encoding="utf-8")
    (tmp_path / "0002_b.py").write_text('revision = "0002"\n', encoding="utf-8")
    (tmp_path / "0003_c.py").write_text("down_revision = None\n", encoding="utf-8")
    # A MAPPING, revision id -> the files claiming it. It returned `set[str]`
    # until #318: a set collapses two files declaring the same revision before
    # anything can look at them, so the gate could not report a collision it
    # had already discarded.
    assert tree_revisions(tmp_path) == {"0001": ["0001_a.py"], "0002": ["0002_b.py"]}


@pytest.mark.unit
def test_two_files_claiming_one_revision_are_both_reported(tmp_path: pathlib.Path) -> None:
    """The collision the set was hiding (#318).

    Migrations here are numbered sequentially, so two branches each adding
    "the next one" both add `0047`, and merging them puts two files with the
    same id in one tree.
    """
    (tmp_path / "0047_from_branch_a.py").write_text('revision = "0047"\n', encoding="utf-8")
    (tmp_path / "0047_from_branch_b.py").write_text('revision: str = "0047"\n', encoding="utf-8")

    found = tree_revisions(tmp_path)

    # BOTH filenames, and sorted, so the report does not depend on the order
    # the filesystem happens to yield.
    assert found == {"0047": ["0047_from_branch_a.py", "0047_from_branch_b.py"]}


@pytest.mark.unit
def test_a_collision_in_the_mounted_tree_is_a_mismatch(monkeypatch, tmp_path, capsys) -> None:
    """...and the gate FIRES on it rather than proceeding to the database.

    Checked before the database is consulted, because it is true of the mounted
    tree alone.
    """
    import check_mount_matches_database as mod

    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0047_a.py").write_text('revision = "0047"\n', encoding="utf-8")
    (versions / "0047_b.py").write_text('revision = "0047"\n', encoding="utf-8")

    monkeypatch.setattr(mod.pathlib.Path, "resolve", lambda self: self, raising=False)
    monkeypatch.setattr(mod, "__file__", str(tmp_path / "scripts" / "x.py"))
    monkeypatch.setenv("DATABASE_URL", "postgresql://unreachable/never-used")
    # If the database WERE consulted this would raise; it must not be reached.
    monkeypatch.setattr(
        mod,
        "database_revision",
        lambda url: (_ for _ in ()).throw(AssertionError("the database must not be consulted")),
    )

    assert mod.main() == EXIT_MISMATCH
    err = capsys.readouterr().err
    assert "SAME REVISION ID" in err
    # Both files named. A message naming one of them sends the reader to
    # renumber the wrong file.
    assert "0047_a.py" in err and "0047_b.py" in err
    # And it says what the database cannot settle, so nobody goes looking there.
    assert "stores a version string" in err


@pytest.mark.unit
def test_the_passing_message_does_not_claim_the_pair_was_verified(
    monkeypatch, tmp_path, capsys
) -> None:
    """The half of #318 that is NOT detectable, kept honest in the copy.

    The old message was "tree and database agree on revision 0047". All that
    was checked is that the id is PRESENT here. Two worktrees numbering the
    next migration identically produce a matching id over different files, and
    `alembic_version` stores nothing that could tell them apart -- so the
    sentence asserted something this check cannot know, in the log a reader
    reaches a minute later when the first request 500s on UndefinedColumn.

    This pins the ABSENCE of the over-claim, which is the only thing a test can
    do about a limit that cannot be closed.
    """
    import check_mount_matches_database as mod

    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0047_only.py").write_text('revision = "0047"\n', encoding="utf-8")

    monkeypatch.setattr(mod.pathlib.Path, "resolve", lambda self: self, raising=False)
    monkeypatch.setattr(mod, "__file__", str(tmp_path / "scripts" / "x.py"))
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(mod, "database_revision", lambda url: "0047")

    assert mod.main() == EXIT_OK
    out = capsys.readouterr().out
    assert "agree" not in out, (
        "the passing message claims the tree and database AGREE. It only "
        "established that the stamped id is present here, which is a weaker "
        "claim and the gap between them is a whole failure mode."
    )
    # What it must say instead: what was compared, and where it read.
    assert "0047" in out
    assert "0047_only.py" in out
    assert str(versions) in out


@pytest.mark.unit
def test_a_revision_the_tree_has_is_not_a_mismatch(monkeypatch, tmp_path) -> None:
    """THE PASSING STATE. Without this the guard is only observed firing."""
    import check_mount_matches_database as mod

    monkeypatch.setattr(mod, "database_revision", lambda url: "0002")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(mod.pathlib.Path, "resolve", lambda self: self, raising=False)
    (tmp_path / "alembic" / "versions").mkdir(parents=True)
    (tmp_path / "alembic" / "versions" / "0002_b.py").write_text(
        'revision = "0002"\n', encoding="utf-8"
    )
    monkeypatch.setattr(mod, "__file__", str(tmp_path / "scripts" / "x.py"))
    assert mod.main() == EXIT_OK


@pytest.mark.unit
def test_a_revision_the_tree_lacks_is_a_mismatch(monkeypatch, tmp_path, capsys) -> None:
    """THE FIRING STATE, and the message must name BOTH values.

    "Can't locate revision identified by '0047'" is what alembic says and it is
    why this check exists: it reads as a missing file. The replacement has to
    say which tree and which database, or it inherits the same wrong search.
    """
    import check_mount_matches_database as mod

    monkeypatch.setattr(mod, "database_revision", lambda url: "0047")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    (tmp_path / "alembic" / "versions").mkdir(parents=True)
    (tmp_path / "alembic" / "versions" / "0046_b.py").write_text(
        'revision = "0046"\n', encoding="utf-8"
    )
    monkeypatch.setattr(mod, "__file__", str(tmp_path / "scripts" / "x.py"))
    assert mod.main() == EXIT_MISMATCH
    err = capsys.readouterr().err
    assert "0047" in err and "0046" in err, (
        "the message must carry BOTH the database's revision and the tree's, "
        "or the reader cannot tell which side is stale"
    )
    assert "mount" in err.lower(), "the message must name the MOUNT as the cause"


@pytest.mark.unit
def test_an_unstamped_database_is_not_a_mismatch(monkeypatch, tmp_path) -> None:
    """A fresh volume has no `alembic_version` row. `upgrade head` is correct."""
    import check_mount_matches_database as mod

    monkeypatch.setattr(mod, "database_revision", lambda url: None)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    (tmp_path / "alembic" / "versions").mkdir(parents=True)
    (tmp_path / "alembic" / "versions" / "0001_a.py").write_text(
        'revision = "0001"\n', encoding="utf-8"
    )
    monkeypatch.setattr(mod, "__file__", str(tmp_path / "scripts" / "x.py"))
    assert mod.main() == EXIT_OK


@pytest.mark.unit
@pytest.mark.parametrize("make_versions", [False, True], ids=["absent", "empty"])
def test_it_cannot_look_and_says_so(monkeypatch, tmp_path, make_versions) -> None:
    """`2`, not `0` and not `1`.

    With no revisions to compare against, every database looks wrong. Reporting
    that as a mismatch would block every start; reporting it as agreement is
    "I could not look" wearing "nothing to complain about".
    """
    import check_mount_matches_database as mod

    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    if make_versions:
        (tmp_path / "alembic" / "versions").mkdir(parents=True)
    monkeypatch.setattr(mod, "__file__", str(tmp_path / "scripts" / "x.py"))
    assert mod.main() == EXIT_COULD_NOT_LOOK


@pytest.mark.unit
def test_an_unreachable_database_cannot_look(monkeypatch, tmp_path) -> None:
    import check_mount_matches_database as mod

    def boom(url):
        raise OSError("connection refused")

    monkeypatch.setattr(mod, "database_revision", boom)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    (tmp_path / "alembic" / "versions").mkdir(parents=True)
    (tmp_path / "alembic" / "versions" / "0001_a.py").write_text(
        'revision = "0001"\n', encoding="utf-8"
    )
    monkeypatch.setattr(mod, "__file__", str(tmp_path / "scripts" / "x.py"))
    assert mod.main() == EXIT_COULD_NOT_LOOK

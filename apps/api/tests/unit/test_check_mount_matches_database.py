"""The mount check must fire on a mismatch AND pass on agreement (#gate).

A guard observed only firing is half-tested: watching it fire proves it fires,
not that it passes. A typo that halts unconditionally leaves every container
dead on arrival, and that symptom is indistinguishable from the hazard the
guard exists to catch — the api crash-loops either way.

So both states are exercised here, and so is every "could not look" branch,
because this check sits in front of `alembic upgrade head` in the api's
startup command: an exit it gets wrong stops the stack.

That sentence was FALSE when it was written, which is the more useful half of
it. `main` has four could-not-look branches and this file exercised three: the
`DATABASE_URL is unset` branch was reached by nothing, because every test here
calls `monkeypatch.setenv("DATABASE_URL", ...)` in its setup. Deleting that
branch outright left the file green. It is the branch a developer hits in the
most ordinary way possible -- running the gate by hand outside compose -- and
the claim that every branch was covered is what stopped anyone counting them.

Each of the four also asserted its exit CODE and no message. Exit 2 is what
all four return and is also what the crash handler returns, so the code alone
does not say which branch ran, or that a branch ran at all: the four could
have been collapsed into one, or rewired to any other cause, with this file
green. Every one now pins the sentence it prints.

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


class _DatabaseWasConsulted(BaseException):
    """Raised by a stub that must never be called, and NOT an `Exception`.

    `main` catches `Exception` around `database_revision` and relabels it "the
    database was unreachable". A sentinel deriving from `Exception` is
    therefore swallowed by the very code it is watching: the guard's message
    is replaced by a message about the network, and the reader is sent to
    check connectivity rather than the ordering regression that actually
    happened.

    Deriving from `BaseException` puts it outside that handler, so it reaches
    pytest with its own name.
    """


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
    # If the database WERE consulted this must raise OUT of `main`, and that is
    # why it is a `BaseException` rather than the `AssertionError` written
    # first.
    #
    # `main` wraps `database_revision(url)` in `except Exception` -- correctly,
    # since an unreachable database is a could-not-look. An `AssertionError`
    # raised by this stub is an `Exception`, so it was caught there, relabelled
    # "the database was unreachable" and returned as exit 2. The guard's own
    # message could never surface. The test would still have failed, on the
    # exit code -- but it would have failed SAYING THE DATABASE WAS
    # UNREACHABLE, pointing the next reader at the network instead of at the
    # ordering regression the guard exists to name.
    monkeypatch.setattr(
        mod,
        "database_revision",
        lambda url: (_ for _ in ()).throw(_DatabaseWasConsulted()),
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
    #
    # ANCHORED, and the ATTRIBUTION matters more than the anchoring.
    #
    # A bare `"0047" in out` is weak for a reason specific to this output: the
    # message also names the FILE, `0047_only.py`, so the needle is satisfied
    # by the filename even if the revision were wrong.
    #
    # **`check_test_integrity` did NOT catch that, and cannot.** TI002 fires
    # only where the needle is an explicit `str(...)` call or an f-string --
    # `_is_explicitly_stringified` returns False for an `ast.Constant`, and the
    # gate's own `test_accepts_a_plain_string_literal_needle` pins that a plain
    # literal is accepted. MEASURED on this branch: restoring `"0047" in out`
    # and running the gate returns `test-integrity: clean`, exit 0.
    #
    # An earlier version of this comment credited the gate with the catch. That
    # is a false assurance about a gate's COVERAGE, written into the material a
    # reader calibrates against -- someone would leave the next bare-literal
    # needle unanchored believing TI002 covers it, and TI002 deliberately does
    # not (widening it to bare names was measured at 36 false positives against
    # 2 real ones).
    #
    # What the gate DID catch is one line below: `assert str(versions) in out`,
    # an explicit `str(...)` with no literal anchor. One finding, reported twice
    # at shifted line numbers as the comment above grew -- which is how it came
    # to be read as two.
    assert "revision 0047 is stamped in the database" in out
    assert "present in the mounted tree (0047_only.py)" in out
    # Anchored to its CLAUSE, not just present somewhere: the path has to be
    # what the message says it read from.
    assert f"read from {versions}" in out


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
@pytest.mark.parametrize(
    ("make_versions", "needle"),
    [
        (False, "no migrations directory at"),
        (True, "contains no migration with a `revision = ...` line"),
    ],
    ids=["absent", "empty"],
)
def test_it_cannot_look_and_says_so(monkeypatch, tmp_path, make_versions, needle, capsys) -> None:
    """`2`, not `0` and not `1`.

    With no revisions to compare against, every database looks wrong. Reporting
    that as a mismatch would block every start; reporting it as agreement is
    "I could not look" wearing "nothing to complain about".

    These two are DIFFERENT branches with different remedies -- a directory
    that is not there, and one that is there and says nothing -- and they were
    parametrized over one assertion on the exit code, which both return and
    which the crash handler also returns. Each now pins its own sentence, so
    collapsing the two into one would go red.
    """
    import check_mount_matches_database as mod

    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    if make_versions:
        (tmp_path / "alembic" / "versions").mkdir(parents=True)
    monkeypatch.setattr(mod, "__file__", str(tmp_path / "scripts" / "x.py"))
    assert mod.main() == EXIT_COULD_NOT_LOOK
    assert needle in capsys.readouterr().err


@pytest.mark.unit
def test_an_unset_DATABASE_URL_cannot_look(monkeypatch, tmp_path, capsys) -> None:
    """THE BRANCH NOTHING REACHED, and the one a developer hits first.

    Every other test in this file calls `monkeypatch.setenv("DATABASE_URL",
    ...)` as setup, so this branch was exercised by nothing -- delete it and
    the file stayed green -- while the module docstring said every
    could-not-look branch was covered. A fixture that supplies the very
    precondition the branch is about is the setup-performs-the-step shape,
    arriving through a `setenv` nobody reads as an assertion.

    It matters beyond bookkeeping: the gate runs in the api's startup command
    where compose supplies the variable, so the only people who meet this
    branch are running it by hand, which is exactly when a wrong exit code is
    read as "the tree is fine".
    """
    import check_mount_matches_database as mod

    monkeypatch.delenv("DATABASE_URL", raising=False)
    versions = tmp_path / "alembic" / "versions"
    versions.mkdir(parents=True)
    (versions / "0001_a.py").write_text('revision = "0001"\n', encoding="utf-8")
    monkeypatch.setattr(mod, "__file__", str(tmp_path / "scripts" / "x.py"))

    assert mod.main() == EXIT_COULD_NOT_LOOK
    assert "DATABASE_URL is unset" in capsys.readouterr().err


@pytest.mark.unit
def test_an_unreachable_database_cannot_look(monkeypatch, tmp_path, capsys) -> None:
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
    # The message AND the cause it reports. A bare `"could not look"` is in all
    # four branches, so it would not distinguish this one from the three above.
    err = capsys.readouterr().err
    assert "the database was unreachable" in err
    assert "OSError: connection refused" in err


@pytest.mark.unit
@pytest.mark.parametrize("args", [["--help"], ["--db", "x"], ["extra"], [""]])
def test_any_argument_is_could_not_look_and_is_named(monkeypatch, capsys, args) -> None:
    """#597: the gate takes no arguments, so ANY argument is exit 2, named.

    Refused before anything is read: the database stub raises a BaseException,
    which escapes `main`'s `except Exception` and fails this test if reached.
    """
    import check_mount_matches_database as mod

    class _Reached(BaseException):  # not Exception, so `main` cannot swallow it
        pass

    def _reached(*_a, **_k):
        # Not KeyboardInterrupt: pytest reads that as the run being interrupted
        # (exit 2), not as this test failing.
        raise _Reached("the database was consulted")

    monkeypatch.setattr(mod, "database_revision", _reached)
    rc = mod.main(["check_mount_matches_database.py", *args])
    err = capsys.readouterr().err
    assert rc == 2, err
    assert "this gate takes no arguments, and was given " + repr(args) in err, err


@pytest.mark.unit
def test_the_command_line_passes_its_arguments_to_main() -> None:
    """The WIRING: `__main__` must hand `sys.argv` to `main`, or the guard above
    never sees a real command line."""
    import subprocess

    script = _SCRIPTS / "check_mount_matches_database.py"
    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(script), "--nope"], capture_output=True, text=True
    )
    assert proc.returncode == 2, proc.stderr
    assert "this gate takes no arguments, and was given ['--nope']" in proc.stderr, proc.stderr

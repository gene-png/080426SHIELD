"""The mounted tree and the database must agree about which migrations exist.

Run immediately before `alembic upgrade head` in the api container.

## The failure this replaces

`docker-compose.yml` hardcodes `name: shield-v2` and binds `./apps/api:/app`,
so the stack is mounted from **whichever tree last ran `up`** — not from the
tree you are standing in. Apply a migration from a current worktree, then run
`docker compose up` from a stale one, and you get two individually correct
states and one inconsistent pair:

    database stamped   0047
    mounted tree has   0044 0045 0046

`alembic upgrade head` then fails with::

    Can't locate revision identified by '0047'

and the container restarts forever. **That message sends the reader after a
missing migration file**, which is the wrong search: the file exists, in a
different tree. Measured 2026-09-11, and the reader was the person who had
applied the migration twenty minutes earlier.

This check fails first, and names both values and the mount, so the search ends
at the sentence.

## Silent-success branches, enumerated before the first line was written

Every path that exits 0 here, and what the input looked like:

  * **`alembic_version` table absent** — a brand-new database that has never
    been migrated. Legitimate and common (a fresh volume, CI). `alembic upgrade
    head` is exactly the right next step, so exit 0.
  * **`alembic_version` empty** — same case, stamped by nothing yet. Exit 0.
  * **the stamped revision IS in the tree** — the ordinary state, including a
    tree AHEAD of the database, which is what `upgrade head` is for. Exit 0.

## The branch this list did not have, and what it costs (#318)

The bullet above says "IS in the tree", and the code tested exactly that, and
then printed **"tree and database agree on revision 0047"**. Those are not the
same claim. An id being PRESENT does not make it the SAME MIGRATION.

This repo numbers migrations sequentially, so two worktrees each writing "the
next one" both write `0047`. Mount the wrong one and:

    database stamped   0047   <- worktree A's migration, already applied
    mounted tree has   0047   <- worktree B's, a different file entirely

The id matches. The check printed a reassuring sentence. `upgrade head` then
does nothing, because the database is already stamped at head, and the first
request 500s on `psycopg.errors.UndefinedColumn` — into the same log this
check had just written its agreement into.

**Half of that is now detectable and is detected; half is not, and is stated
rather than implied.**

  * **Two files in the MOUNTED tree claiming one revision id** — exit 1,
    naming both files. This is what a merge of those two worktrees' branches
    produces, and it was previously invisible for a reason worth recording:
    `tree_revisions` returned a `set`, and a set deduplicates in silence. The
    check could not have reported a collision it had already collapsed.
    MEASURED 2026-09-20: 48 migration files, 48 distinct ids, so this is
    LATENT today rather than live — the hole opens on the next merge of two
    branches that each added a migration.

  * **One file here, a different file there, never merged** — NOT detectable
    with the data available. `alembic_version` stores a version string and
    nothing about the migration's content, so the two trees are
    indistinguishable from inside this container. The message no longer claims
    otherwise: it says which revision was found and where it read it, and
    leaves "agree" unsaid. What WOULD detect it is comparing the live schema
    against the models AFTER `upgrade head`, which is a different check with a
    different failure mode (a tree legitimately ahead of the database would
    trip it here). Tracked rather than bolted on.

And the paths that do not:

  * **the stamped revision is NOT in the tree** — exit 1, the defect.
  * **the versions directory is missing or empty** — exit 2. This is "I could
    not look": with no revisions to compare against, every database would look
    wrong. It must not share an exit with either answer.
  * **the database cannot be reached** — exit 2, same reason. `depends_on`
    waits for `service_healthy`, so this should not happen; if it does, the
    honest report is that the check did not run, not that the pair is fine.
  * **any command-line argument** — exit 2, naming it (#597). The gate takes
    none, so `--help` or a typo must not run the check as though absent.

## Why not just read alembic's own error

Because it is about a revision, and the defect is about a MOUNT. Alembic
cannot know the tree it is reading is not the tree that was migrated from —
that fact lives in the relationship between a compose file and a directory,
which is the same place the isolation defect in `CLAUDE.md` lived.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

EXIT_OK = 0
EXIT_MISMATCH = 1
EXIT_COULD_NOT_LOOK = 2

#: A migration's own revision id, at module top level. BOTH spellings this repo
#: actually uses:
#:
#:     revision: str = "0045"      <- 45 of the migrations
#:     revision = "0046"           <- the rest
#:
#: The annotation is optional in the pattern because a first draft required its
#: ABSENCE and matched exactly one file out of 46. That is worse than not
#: having this check: a database stamped at any of the other 45 would have been
#: reported as a mismatch and the api would have refused to start. Caught by
#: reading the check's own output in its firing state -- the exit code was
#: correct and the finding inside it was wrong.
#:
#: Read from the FILES rather than by importing them: importing runs module
#: code, and a tree this check exists to distrust is not a tree to execute.
_REVISION = re.compile(r"^revision(?:\s*:\s*str)?\s*=\s*['\"]([^'\"]+)['\"]", re.M)


def tree_revisions(versions_dir: pathlib.Path) -> dict[str, list[str]]:
    """Revision id -> the filenames claiming it.

    A MAPPING rather than a set, and that is the point. The first version
    returned `set[str]`, so two files both declaring `revision = "0047"`
    collapsed into one entry before anything could look at them -- the check
    could not report a collision it had already discarded. Same shape as a
    Python dict silently keeping the last duplicate key, which this repo has
    also been bitten by.

    Sorted, so the reported filenames do not depend on filesystem order.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(versions_dir.glob("*.py")):
        match = _REVISION.search(path.read_text(encoding="utf-8", errors="replace"))
        if match:
            found.setdefault(match.group(1), []).append(path.name)
    return found


def database_revision(url: str) -> str | None:
    """The stamped revision, or None when nothing has been stamped yet."""
    from sqlalchemy import create_engine, text

    engine = create_engine(url)
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM information_schema.tables " "WHERE table_name = 'alembic_version'")
        ).first()
        if not exists:
            return None
        row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
        return row[0] if row else None


def main(argv: list[str] | None = None) -> int:
    # It takes NO arguments, and any it is given is a could-not-look (#597). A
    # flag this gate does not implement must not run the check as though it
    # were absent: `--help` or a typo'd `--db` would otherwise print a verdict
    # the caller did not ask for. `None` (a direct call, as the tests make) is
    # no arguments; the command line passes `sys.argv`, program name first.
    args = [] if argv is None else list(argv[1:])
    if args:
        print(
            f"check-mount: could not look -- this gate takes no arguments, and was "
            f"given {args!r}. Run it bare: `python scripts/check_mount_matches_database.py`.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK
    here = pathlib.Path(__file__).resolve().parents[1]
    versions = here / "alembic" / "versions"

    if not versions.is_dir():
        print(
            f"check-mount: could not look -- no migrations directory at {versions}. "
            f"With nothing to compare against, every database would look wrong, so "
            f"this is not reported as a mismatch.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    by_revision = tree_revisions(versions)
    in_tree = set(by_revision)
    if not in_tree:
        print(
            f"check-mount: could not look -- {versions} contains no migration with a "
            f"`revision = ...` line. Either the directory is empty or the format "
            f"changed; both need a human before this check can mean anything.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    collisions = {rev: files for rev, files in by_revision.items() if len(files) > 1}
    if collisions:
        # Reported BEFORE the database is consulted, because it is true of the
        # mounted tree alone and because alembic will refuse this tree anyway --
        # with a message about revisions rather than about files.
        lines = [
            "",
            "check-mount: TWO MIGRATIONS IN THIS TREE CLAIM THE SAME REVISION ID.",
            "",
        ]
        for rev, files in sorted(collisions.items()):
            lines.append(f"  revision {rev} : {', '.join(files)}")
        lines += [
            "",
            f"  reading        : {versions}",
            "",
            "Migrations here are numbered sequentially, so two branches that each",
            "added `the next one` both added the same number, and merging them",
            "produced this. One of these files has to be renumbered and have its",
            "`down_revision` re-pointed -- the DATABASE cannot tell you which,",
            "because it stores a version string and nothing about the content.",
            "",
        ]
        print("\n".join(lines), file=sys.stderr)
        return EXIT_MISMATCH

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("check-mount: could not look -- DATABASE_URL is unset.", file=sys.stderr)
        return EXIT_COULD_NOT_LOOK

    try:
        stamped = database_revision(url)
    except Exception as exc:  # noqa: BLE001 - the reason is reported, not swallowed
        print(
            f"check-mount: could not look -- the database was unreachable: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

    if stamped is None:
        print(
            f"check-mount: database carries no alembic stamp yet; "
            f"{len(in_tree)} revision(s) in the tree. Nothing to disagree about."
        )
        return EXIT_OK

    if stamped in in_tree:
        # NOT "tree and database agree". What was checked is that the stamped id
        # is PRESENT here, which is a weaker claim, and the gap between the two
        # is a whole failure mode (see the module docstring). The message states
        # what was compared and where it looked, so a reader debugging an
        # UndefinedColumn a minute later is not told this pair was verified.
        print(
            f"check-mount: revision {stamped} is stamped in the database and present "
            f"in the mounted tree ({by_revision[stamped][0]}); "
            f"{len(in_tree)} revision(s) read from {versions}."
        )
        return EXIT_OK

    newest = sorted(in_tree)[-1]
    print(
        "\n".join(
            [
                "",
                "check-mount: THE MOUNTED TREE IS NOT THE TREE THIS DATABASE WAS",
                "MIGRATED FROM.",
                "",
                f"  database stamped : {stamped}",
                f"  newest in tree   : {newest}",
                f"  tree has         : {' '.join(sorted(in_tree))}",
                f"  reading          : {versions}",
                "",
                "`alembic upgrade head` is about to fail with \"Can't locate revision",
                f"identified by '{stamped}'\", which reads as a missing file. The file is",
                "not missing -- it is in a different tree.",
                "",
                "`docker-compose.yml` binds `./apps/api:/app` under a hardcoded project",
                "name, so the stack is mounted from whichever tree last ran `up`, not",
                "from the one you are standing in. Either bring this tree up to the",
                "revision the database holds, or re-run `up` from the tree you migrated",
                "from.",
                "",
            ]
        ),
        file=sys.stderr,
    )
    return EXIT_MISMATCH


if __name__ == "__main__":
    # A crash must not share an exit code with "found something": Python exits 1
    # on an unhandled exception, which is this gate's violation code.
    #
    # Duplicated verbatim in every gate rather than shared -- an import is one
    # more thing that can fail BEFORE the handler is installed, which is the
    # defect this block exists to close. Drift is caught instead by
    # tests/unit/test_gate_crash_exit_code.py, which runs every one of them.
    #
    # It also carries the marker `discover_gates` keys on, so adding it is what
    # puts this script into `check_gate_fixtures.py`'s registry. Both harnesses
    # that prove a gate can fail were blind to it (#318), and the "gates can
    # fail" step was green BECAUSE of the omission.
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-mount-matches-database: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(2) from exc

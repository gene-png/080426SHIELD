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

And the paths that do not:

  * **the stamped revision is NOT in the tree** — exit 1, the defect.
  * **the versions directory is missing or empty** — exit 2. This is "I could
    not look": with no revisions to compare against, every database would look
    wrong. It must not share an exit with either answer.
  * **the database cannot be reached** — exit 2, same reason. `depends_on`
    waits for `service_healthy`, so this should not happen; if it does, the
    honest report is that the check did not run, not that the pair is fine.

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


def tree_revisions(versions_dir: pathlib.Path) -> set[str]:
    found: set[str] = set()
    for path in versions_dir.glob("*.py"):
        match = _REVISION.search(path.read_text(encoding="utf-8", errors="replace"))
        if match:
            found.add(match.group(1))
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


def main() -> int:
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

    in_tree = tree_revisions(versions)
    if not in_tree:
        print(
            f"check-mount: could not look -- {versions} contains no migration with a "
            f"`revision = ...` line. Either the directory is empty or the format "
            f"changed; both need a human before this check can mean anything.",
            file=sys.stderr,
        )
        return EXIT_COULD_NOT_LOOK

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
        print(f"check-mount: tree and database agree on revision {stamped}.")
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
    raise SystemExit(main())

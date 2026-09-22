"""A blank `legal_name` is the same absence as NULL (#254 follow-up, D-080)

Revision ID: 0050
Revises: 0049
Create Date: 2026-09-22 00:00:00

D-080 made `Client.legal_name` nullable and established, at every writer, that
an unnamed organisation stores NULL rather than blanks. **That is a write-time
invariant and 0049 did not establish it for rows that already existed.** Its
three backfill predicates match a mapped domain, a primary contact's display
name, and the literal old sentinel — none of them matches whitespace.

So a row written by any pre-D-080 `PATCH /intake` could hold `"   "`, and
`ClientProfilePatch` carries no validator that would have stopped it.

## Why that is not cosmetic

`"   "` is TRUTHY. Deliverable exporters resolved the organisation line with
`client_legal_name or "Client"`, so a blank never reached the fallback: it
rendered as EMPTY on the client's DOCX, PDF and XLSX, where their name belongs,
while the admin UI called the same row unnamed because the web helper trims.

The companion change routes every such reader through `app/client_naming.py`.
This migration removes the state rather than defending against it, so the two
are deliberately not alternatives.

## THE PREDICATE IS PYTHON, NOT SQL, AND THAT IS THE WHOLE POINT

The first version of this migration was one statement:

    UPDATE client SET legal_name = NULL
     WHERE legal_name IS NOT NULL AND trim(legal_name) = ''

**Single-argument `trim()` strips the SPACE character and nothing else**, on
both engines. Measured 2026-09-22 — SQLite in-memory and the dev Postgres 16,
same five inputs:

    input        SQLite trim()=''   PG trim()=''   Python .strip() empty
    "   "            True                t                True
    "\\t"             False               f                True
    "\\n"             False               f                True
    "\\t\\n "          False               f                True
    NBSP U+00A0      False               f                True

Four of the five whitespace classes that `is_named_org` treats as blank were
**invisible to the SQL predicate on both engines**, and the docstring asserted
the opposite: *"a row whose name trims to empty carries no name under any
reading"*. The word "trims" meant two different classes in one file.

**NBSP is the one that actually arrives.** `CLAUDE.md` records that a narrow
no-break space is exactly what PDF and Word extraction emit — which is how
intake fields get filled from a client's existing documents. The most likely
real blank in this column was the one furthest from the predicate.

**And the failure was silent in the way that matters**: a `"\\t"` row left this
migration logging `normalised 0 blank legal_name row(s)`, byte-identical to
what a clean database logs. Nothing in that line could tell you it had missed.

So the normalisation runs in Python, and `str.strip()` — the LANGUAGE's
definition of whitespace — is the single shared definition. `is_named_org` is
`bool(x and x.strip())`, so both rest on the same call rather than on two
descriptions of it. The two-argument SQL form `trim(legal_name, <charset>)`
works on both engines and was refused: it re-creates a hand-enumerated
character class, which is the `_HSPACE` defect this repo records being wrong by
sixteen characters with nothing able to see it. Let the language define the set.

This migration does NOT import `app.client_naming`. A migration that imports
application code breaks when that code moves, and the shared thing here is
`str.strip()` itself, not a function — which is what makes this a derivation
rather than a synchronisation.

## Blast radius, measured before choosing

No schema change: the column's type and nullability are untouched, so no read
path gains a value it could not already receive. What changes is the VALUE of
rows whose name is blank, and NULL is what every one of them already means.

MEASURED against the dev Postgres, 2026-09-22, before this revision:

    SELECT count(*) FROM client;                                        -> 4
    SELECT count(*) FROM client WHERE legal_name IS NULL;               -> 1
    SELECT count(*) FROM client
     WHERE legal_name IS NOT NULL AND trim(legal_name) = '';            -> 0

Zero on dev says nothing about any other deployment, which is why this logs its
own rowcount rather than asserting an expected one. Dev was reseeded; a
long-lived database is exactly where a blank would be. Note the third query is
the SPACE-ONLY one above, so it is a floor: it cannot see a tab or an NBSP row,
which is the defect this file now exists to record.

**There is no false-positive case.** A row whose name is empty after
`str.strip()` carries no name under any reading — unlike 0049's predicates,
which had to reconstruct an intention, this one tests the value itself. That is
why it needs no `intake_completed_at` qualifier: a blank is a blank whether or
not intake was submitted.

## Downgrade

Irreversible by design, and it does nothing rather than pretending otherwise.
The rows it changed are indistinguishable afterwards from rows that were always
NULL, and restoring `"   "` to an arbitrary subset would invent data.

That is safe against 0049's own downgrade, which runs
`UPDATE client SET legal_name = '(pending intake)' WHERE legal_name IS NULL`
BEFORE restoring `nullable=False` — so a row this migration NULLed becomes the
sentinel on the way back, which is consistent with what 0049 means by it.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    conn = op.get_bind()

    # Read, decide in PYTHON, write back by id. `str.strip()` is the shared
    # definition of blank -- see the docstring for why this is not one SQL
    # statement, and for the measurement that made it three.
    rows = conn.execute(
        sa.text("SELECT id, legal_name FROM client WHERE legal_name IS NOT NULL")
    ).fetchall()

    # `row[1] or ""` rather than `str(row[1])`: `str(None)` is the four-character
    # string "None", which is NOT blank -- so if the `WHERE legal_name IS NOT
    # NULL` above were ever relaxed, `str()` would silently classify every NULL
    # row as NAMED. That is a fail-OPEN coupling between two lines that do not
    # look related, and it costs nothing to remove.
    blank_ids = [row[0] for row in rows if not (row[1] or "").strip()]

    for blank_id in blank_ids:
        conn.execute(
            sa.text("UPDATE client SET legal_name = NULL WHERE id = :id"),
            {"id": blank_id},
        )

    # Logged after the writes that make it true, and it reports the SCANNED
    # total as well: "0 of 0" and "0 of 400" are different facts, and the
    # single-number version of this line could not tell them apart.
    log.info(
        "0050: normalised %s blank legal_name row(s) to NULL, of %s non-NULL scanned",
        len(blank_ids),
        len(rows),
    )


def downgrade() -> None:
    # Deliberately a no-op. See the module docstring: the rows this touched are
    # now indistinguishable from rows that were always NULL, and re-inserting
    # blanks would fabricate a distinction the data no longer carries.
    log.info("0050 downgrade: no-op by design; a normalised blank cannot be un-normalised")

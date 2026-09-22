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

`"   "` is TRUTHY. Every deliverable exporter resolves the organisation line
with `client_legal_name or "Client"`, so a blank name never reaches the
`"Client"` fallback: it renders as EMPTY on the client's DOCX, PDF and XLSX,
where their name belongs. The admin UI calls the same row unnamed, because the
web helper trims. Two definitions of "named" disagreeing about one row is the
exact defect D-080 exists to close, and it survived D-080 at the read end.

The companion change normalises the six readers that reach a deliverable. This
migration removes the state rather than defending against it, so the two are
deliberately not alternatives: the readers stop a blank that arrives some other
way, and this stops the blanks that are already stored.

## Blast radius, measured before choosing

Widening is not at issue here — the column's type is unchanged and no read path
gains a value it could not receive. What changes is the VALUE of rows whose
name is blank, and NULL is what every one of them already means.

MEASURED against the dev Postgres, 2026-09-22, before this revision, via
`docker compose exec -T db psql -U shield -d shield -At -c "<the statement>"`:

    SELECT count(*) FROM client WHERE legal_name IS NOT NULL AND trim(legal_name) = '';
      -> 0

Zero on dev says nothing about any other deployment, which is why this logs its
own rowcount rather than asserting an expected one. Dev has no pre-D-080 blank
because it was reseeded; a long-lived database is exactly where one would be.

**There is no false-positive case.** A row whose name trims to empty carries no
name under any reading — unlike 0049's predicates, which had to reconstruct an
intention, this one tests the value itself. That is why it needs no
`intake_completed_at` qualifier: a blank is a blank whether or not intake was
submitted.

## Portability

`trim()` is standard SQL and present on both SQLite and Postgres, which is the
pair `CLAUDE.md` core principle 6 requires. No schema change, so no
`batch_alter_table` is needed.

## Downgrade

Irreversible by design, and it does nothing rather than pretending otherwise.
The rows it changed are indistinguishable afterwards from rows that were always
NULL, and restoring `"   "` to an arbitrary subset would invent data. A
downgrade that silently does nothing is honest here; one that guessed would not
be.
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
    # Logged AFTER the statement that makes it true, from the driver's own
    # rowcount, rather than from a SELECT taken beforehand.
    result = conn.execute(
        sa.text(
            "UPDATE client SET legal_name = NULL "
            " WHERE legal_name IS NOT NULL AND trim(legal_name) = ''"
        )
    )
    log.info("0050: normalised %s blank legal_name row(s) to NULL", result.rowcount)


def downgrade() -> None:
    # Deliberately a no-op. See the module docstring: the rows this touched are
    # now indistinguishable from rows that were always NULL, and re-inserting
    # blanks would fabricate a distinction the data no longer carries.
    log.info("0050 downgrade: no-op by design; a normalised blank cannot be un-normalised")

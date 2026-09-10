"""Persist what a Risk Register was synthesized from (#240)

Revision ID: 0047
Revises: 0046
Create Date: 2026-09-10 00:00:00

#237's fix (#242) refuses GENERATION from unapproved assessments. `export` is
unguarded, and export is the path in #237's own title: a register generated
last week from a DRAFT ATT&CK mapping sits with `finalized_at IS NULL`, a
consultant clicks Export, and it finalizes and appears on the client's
dashboard.

**And `export` could not check even if it wanted to.** Nothing on
`risk_registers` recorded which assessments -- or which versions, or which
statuses -- the register was synthesized from.

## Why a guard at export time would be the wrong fix

Recomputing "were the inputs approved?" at export reads TODAY's statuses. A ZT
assessment approved AFTER generation would let the export certify coverage over
a register that never saw it. That is D-053's snapshot-versus-live lesson: the
guarantee needs to know what the state WAS, not what it has become.

So the provenance is written at GENERATE time and read at export.

## What pre-migration rows get: NULL, and NULL means "not recorded"

Every register written before this migration was synthesized from inputs whose
statuses were never captured, and no SQL recovers them. Backfilling `{}` --
"nothing was excluded" -- would write a clean bill of health the database
cannot know into the column whose entire purpose is recording what actually
happened.

`CLAUDE.md`: **missing data defaults to UNCONFIRMED, never to confirmed.** Same
call 0046 made one table over, and the same reason #59 is the standing evidence
for why the silent-fallback version is the trap.

The consequence is deliberate and is handled in the route rather than here: a
register with NULL provenance cannot be certified, so `export` says so instead
of assuming either answer.

## Blast radius, measured before choosing

    SELECT count(*) FROM risk_registers WHERE finalized_at IS NULL;
    -> 0 of 1, dev database, 2026-09-10

Zero unfinalized registers, so nothing in this database is mid-flight through
the hole. That made a dated residual defensible and is NOT why the real fix was
written: the persisted field is what unblocks the two CLIENT-FACING surfaces
#240 names -- the exported documents and `clients.py::risk_dashboard` -- which
a guard alone would leave uncaveated.

## TO WHOEVER WRITES THE NEXT MIGRATION THAT TOUCHES THIS COLUMN

Do not backfill it. A NULL here is a fact about what was recorded, and it is
load-bearing: the route branches on it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("risk_registers") as batch_op:
        batch_op.add_column(
            sa.Column(
                "provenance",
                sa.JSON(),
                nullable=True,
                # No server_default ON PURPOSE -- see the module docstring. `{}`
                # would read as "nothing was excluded", which is a clean bill of
                # health for every row that predates this column.
                comment=(
                    "What this register was synthesized FROM, captured at "
                    "generate time: the contributing assessments with their "
                    "version and status as they stood, plus any inputs that "
                    "existed and were excluded. NULL means not recorded "
                    "(pre-0047 rows)."
                ),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("risk_registers") as batch_op:
        batch_op.drop_column("provenance")

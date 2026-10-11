"""Record whether a capability list's extraction attributed every item (#177)

Revision ID: 0058
Revises: 0057
Create Date: 2026-10-02 00:00:00

`tech_debt/reconcile.py`'s `Reconciliation.attribution_complete` decides
whether the per-row exclusion list can be trusted, and it was not stored. The
writer fills `excluded_rows` only when attribution is complete and stores `[]`
when nothing was excluded, so an empty list was the stored form of BOTH
"nothing was excluded" and "attribution failed". Every surface had to report
the commonest case, a clean extraction, as `unknown`; and the case #193 names
-- as many items as rows, two of them claiming one row -- printed "Total
annual cost" over a real exclusion.

## Pre-migration rows stay NULL, and NULL means "not recorded"

The flag was never captured for them and no SQL recovers it. One inference IS
sound, and it is made by the READER, not written here: a NON-EMPTY
`excluded_rows` was only ever written under `if attribution_complete`, so such
a list's attribution was complete. An empty one proves nothing, and NULL with
an empty list reads as unknown -- never as complete
(`tech_debt/reconcile.py::exclusion_count_state`). No backfill writes that
inference into the column: a recorded value and an inferred one would then be
the same bytes.

## Shape

Additive, nullable, **no server-side default** (the C0 pattern, as 0046):
a default would manufacture the value for every pre-migration row and for any
future writer that forgets to set it. Written at INSERT by the extraction job
(`routes/tech_debt.py`), the only writer of a reconciled list.
`batch_alter_table` for SQLite safety. `downgrade()` drops the column exactly;
a down-then-up turns recorded flags back into NULL, which reads as not
recorded, never as complete.

## Blast radius

No read path changes meaning for an existing row: NULL keeps every list
reading as it did before (named drops: exact; otherwise unknown).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0058"
down_revision: str | Sequence[str] | None = "0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("capability_lists") as batch_op:
        batch_op.add_column(
            sa.Column(
                "attribution_complete",
                sa.Boolean(),
                nullable=True,
                # No server_default ON PURPOSE: see the module docstring.
                comment=(
                    "True when the extraction attributed every item to one uploaded "
                    "row. NULL means not recorded (pre-0058 lists, and lists no "
                    "extraction wrote)."
                ),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("capability_lists") as batch_op:
        batch_op.drop_column("attribution_complete")

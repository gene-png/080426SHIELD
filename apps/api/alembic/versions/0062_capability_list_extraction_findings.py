"""Record what a capability list's extraction could not store as given (#833, #834)

Revision ID: 0062
Revises: 0061
Create Date: 2026-10-05 00:00:00

`tech_debt/extract.py::_coerce_item` converted the model's numbers with
`int(float(v))` and `float(v)` and stored strings unbounded. "$1,200" became no
cost, 2.9 licences became 2, `true` became 1, all with no record (#833); and a
string longer than its column crashed the insert on Postgres after the provider
call was paid, losing the whole list (#834). The extraction now refuses a value
it cannot store as given (NULL) or cuts a string to its column, and records each
one here: `{source_row_index, item_name, field, reason, value}`.

The workspace reads the LIST after a run, not the run's result, so a record kept
only on the run would be gone on reload. That is why this is a column.

## NULL means "not recorded"

Lists written before this migration were never checked, so they stay NULL and
read as not recorded, never as "nothing to record". The extraction writes `[]`
when it checked and found nothing. No backfill: the values were already
converted, and no SQL recovers what the model sent.

## Shape

Additive, nullable, **no server-side default** (the C0 pattern, as 0058): a
default would manufacture "checked, nothing found" for every old list.
`batch_alter_table` for SQLite. `downgrade()` drops the column exactly.

## Blast radius

No read path changes meaning for an existing row: NULL renders nothing.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0062"
down_revision: str | Sequence[str] | None = "0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("capability_lists") as batch_op:
        batch_op.add_column(
            sa.Column(
                "extraction_findings",
                sa.JSON(),
                nullable=True,
                # No server_default ON PURPOSE: see the module docstring.
                comment=(
                    "Values the extraction could not store as given, each "
                    "{source_row_index, item_name, field, reason, value}. NULL "
                    "means not recorded (pre-0062 lists)."
                ),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("capability_lists") as batch_op:
        batch_op.drop_column("extraction_findings")

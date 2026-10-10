"""Record the other axes a Risk Register entry directly affects (#806, G1).

Revision ID: 0066
Revises: 0065

Gene's G1, option 3 (#806 record 5982727504): one primary `axis` drives every
count, and a new optional `other_axes` records every other axis the scenario
also directly affects. It never changes a total: `axis_counts` and
`entries_without_axis` stay primary-only (#313).

- `other_axes`: JSON list of `detection` / `prevention` / `response`, ordered
  and de-duplicated by `generate`, never holding the entry's own `axis`.

NULL means "not recorded": every pre-0066 row, and a new row whose model
response carried no readable list (counted in the generate audit row's
`other_axes_dropped`). `[]` is the positive claim "no other axis". The prompt
asking for the field ships in the same change as this column (C11(2), #806
5983938383), so no run of the approved prompt ever had its value dropped.

## Blast radius

Additive, nullable, no server default and no backfill: no existing row changes
meaning, and nothing reads it but the serializers that add it. `batch_alter_table`
for SQLite. The downgrade REFUSES while any row records a value, for 0061's
reason: dropping the column would delete what the model said without a trace.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0066"
down_revision: str | Sequence[str] | None = "0065"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("risk_entries") as batch:
        batch.add_column(sa.Column("other_axes", sa.JSON(), nullable=True))


def downgrade() -> None:
    recorded = (
        op.get_bind()
        .execute(sa.text("SELECT COUNT(*) FROM risk_entries WHERE other_axes IS NOT NULL"))
        .scalar_one()
    )
    if recorded:
        raise RuntimeError(
            f"Refusing to downgrade 0066: {recorded} Risk Register entr"
            f"{'y records' if recorded == 1 else 'ies record'} other axes. "
            "Dropping the column would delete them without a trace."
        )
    with op.batch_alter_table("risk_entries") as batch:
        batch.drop_column("other_axes")

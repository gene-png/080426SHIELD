"""Record who set a Risk Register entry's rating, when a consultant did (#844).

Revision ID: 0061
Revises: 0060

`risk_entries.likelihood` and `impact` were written only by `generate`, from
the model. #844 adds a consultant edit path, because the approved
`risk_synthesize` prompt (#806, G3 option c) returns null where the evidence
cannot support a rating, and an unrated entry has no tier. Once a consultant
can set the pair, `origin = 'ai_generated'` stops describing the rating on an
edited row -- and the XLSX prints that column to the client.

- `rating_edited_by`: the consultant who last set either half (FK users, SET
  NULL, as `attack_coverage.reviewed_by` in 0059).
- `rating_edited_at`: when.

NULL in both means the rating is the model's as generated. That is a true
statement about every pre-0061 row, because no other writer of the pair has
ever existed, so no backfill is needed and none is written.

## Blast radius

Additive, nullable, no server default: no existing row changes meaning.
`batch_alter_table` for SQLite. The downgrade REFUSES while any row records an
edit, for 0059's reason: dropping the columns would make a consultant's rating
read as the model's.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0061"
down_revision: str | Sequence[str] | None = "0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")
_FK = "fk_risk_entries_rating_edited_by_users"


def upgrade() -> None:
    with op.batch_alter_table("risk_entries") as batch:
        batch.add_column(sa.Column("rating_edited_by", _UUID, nullable=True))
        batch.add_column(sa.Column("rating_edited_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(_FK, "users", ["rating_edited_by"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    edited = (
        op.get_bind()
        .execute(sa.text("SELECT COUNT(*) FROM risk_entries WHERE rating_edited_at IS NOT NULL"))
        .scalar_one()
    )
    if edited:
        raise RuntimeError(
            f"Refusing to downgrade 0061: {edited} Risk Register entr"
            f"{'y has' if edited == 1 else 'ies have'} a rating a consultant set. "
            "Dropping the columns would make it read as the model's."
        )
    with op.batch_alter_table("risk_entries") as batch:
        batch.drop_constraint(_FK, type_="foreignkey")
        batch.drop_column("rating_edited_at")
        batch.drop_column("rating_edited_by")

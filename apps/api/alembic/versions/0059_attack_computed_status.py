"""ATT&CK statuses computed from Detect / Prevent / Respond, and their review (#554 R3)

Revision ID: 0059
Revises: 0058
Create Date: 2026-10-02 00:00:00

Gene's decisions on #554 (relayed by the advisor, 2026-10-02): a technique is
Covered only when Detect, Prevent and Respond are all in place, and any other
combination is Partial; the code computes it. The advisor's (d): this applies
only to assessments approved after it ships -- a released assessment keeps
rendering what was delivered, as #620 (0054) did for computed parents.

## `attack_assessments.status_rules`, nullable, additive

* `1` -- approved before R3: render the stored statuses.
* `2` -- approved under R3: compute them. Written at approve.
* NULL -- a draft, not yet approved: computed (it is approved under R3).

`app/attack/rules.py::statuses_computed` is the only reader, and it raises on
any other value rather than defaulting to either rule.

The backfill gives every APPROVED and RELEASED assessment `1`. The status
column stores the enum's NAME, as 0054 measured. DRAFT and DISCARDED stay NULL.
No `attack_coverage` row is written.

## `attack_coverage.reviewed_status` / `reviewed_by` / `reviewed_at`

The advisor's Q1 (22:20Z): on an R3 assessment, a technique whose computed
status differs from the AI's stored suggestion is a review queue, and release
is refused until it has been reviewed. `reviewed_status` is the computed status
a consultant accepted; a row whose computed status later moves away from it is
back in the queue. Who and when sit beside it. All NULL: nothing is reviewed.

SQLite-safe via `batch_alter_table` (core principle 6).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0059"
down_revision: str | Sequence[str] | None = "0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")
_FK = "fk_attack_coverage_reviewed_by_users"


def upgrade() -> None:
    with op.batch_alter_table("attack_assessments") as batch:
        batch.add_column(sa.Column("status_rules", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE attack_assessments SET status_rules = 1 WHERE status IN ('APPROVED', 'RELEASED')"
    )
    with op.batch_alter_table("attack_coverage") as batch:
        batch.add_column(sa.Column("reviewed_status", sa.String(32), nullable=True))
        batch.add_column(sa.Column("reviewed_by", _UUID, nullable=True))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(_FK, "users", ["reviewed_by"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    # REFUSED while anything the columns record would be lost, for 0054's
    # reason: a re-upgrade would backfill every APPROVED and RELEASED row to 1,
    # silently moving an R3 release onto its stored statuses, and a recorded
    # review is who accepted a computed status the release gate read.
    bind = op.get_bind()
    computed = bind.execute(
        sa.text("SELECT COUNT(*) FROM attack_assessments WHERE status_rules = 2")
    ).scalar_one()
    if computed:
        raise RuntimeError(
            f"Refusing to downgrade 0059: {computed} ATT&CK assessment(s) have "
            "status_rules = 2 (approved under R3). Dropping the column would lose "
            "that, and re-upgrading would backfill them to stored statuses (1)."
        )
    reviewed = bind.execute(
        sa.text("SELECT COUNT(*) FROM attack_coverage WHERE reviewed_status IS NOT NULL")
    ).scalar_one()
    if reviewed:
        raise RuntimeError(
            f"Refusing to downgrade 0059: {reviewed} ATT&CK technique(s) have reviewed_status "
            "set, a recorded review of their computed status that dropping the columns "
            "would erase."
        )
    with op.batch_alter_table("attack_coverage") as batch:
        batch.drop_constraint(_FK, type_="foreignkey")
        batch.drop_column("reviewed_at")
        batch.drop_column("reviewed_by")
        batch.drop_column("reviewed_status")
    with op.batch_alter_table("attack_assessments") as batch:
        batch.drop_column("status_rules")

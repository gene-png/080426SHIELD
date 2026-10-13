"""CSF Enterprise roll-up rule recorded per assessment (#1031)

Revision ID: 0070
Revises: 0068
Create Date: 2026-10-12 00:00:00

#1031 (Gene, #736 6115464421): an unscored seed tier no longer takes part in
the CSF Playbook Enterprise roll-up, and the target comes from the scored
tiers only (ruling 2, option (a)). Ruling 3 (#736 6116519635): released
numbers FREEZE -- an assessment approved before #1031 keeps rendering what
was delivered, as 0054 and 0059 did for ATT&CK.

## `csf_assessments.rollup_rules`, nullable, additive

* `1` -- approved before #1031: every in-scope tier rolls up.
* `2` -- approved under #1031: scored tiers only. Written at approve.
* NULL -- not yet approved: scored tiers only.

`app/csf/rules.py::scored_tiers_only` is the only reader, and it raises on any
other value rather than defaulting to either rule.

The backfill gives every APPROVED and RELEASED assessment `1`. The status
column stores the enum's NAME, as 0054 measured. DRAFT, SUBMITTED and
DISCARDED stay NULL.

## Revision chain

Written against main's head 0066, and re-pointed to 0068 in #1077's landing
commit, after N4 (0067) and N5 (0068) merged, in the order the advisor
approved (#736 6128447366 (a)). The merge checklist confirms `alembic heads`
is single.

SQLite-safe via `batch_alter_table` (core principle 6).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0070"
down_revision: str | Sequence[str] | None = "0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("csf_assessments") as batch:
        batch.add_column(sa.Column("rollup_rules", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE csf_assessments SET rollup_rules = 1 WHERE status IN ('APPROVED', 'RELEASED')"
    )


def downgrade() -> None:
    # REFUSED while an assessment was approved under #1031, for 0054's reason:
    # a re-upgrade would backfill it to 1, silently moving a release approved
    # under the scored-tiers rule onto the every-tier rule.
    bind = op.get_bind()
    scored = bind.execute(
        sa.text("SELECT COUNT(*) FROM csf_assessments WHERE rollup_rules = 2")
    ).scalar_one()
    if scored:
        raise RuntimeError(
            f"Refusing to downgrade 0070: {scored} CSF assessment(s) have "
            "rollup_rules = 2 (approved under #1031). Dropping the column would lose "
            "that, and re-upgrading would backfill them to the every-tier rule (1)."
        )
    # Review of #1077, F3: NULL reads as the scored-tiers rule, so an APPROVED
    # or RELEASED row left NULL was approved under it too, and the re-upgrade
    # would backfill it to 1 just the same. Matched on the stored NAME, as the
    # backfill is.
    unrecorded = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM csf_assessments "
            "WHERE rollup_rules IS NULL AND status IN ('APPROVED', 'RELEASED')"
        )
    ).scalar_one()
    if unrecorded:
        raise RuntimeError(
            f"Refusing to downgrade 0070: {unrecorded} APPROVED or RELEASED CSF "
            "assessment(s) have no rollup_rules recorded, which reads as the "
            "scored-tiers rule; re-upgrading would backfill them to the every-tier "
            "rule (1)."
        )
    with op.batch_alter_table("csf_assessments") as batch:
        batch.drop_column("rollup_rules")

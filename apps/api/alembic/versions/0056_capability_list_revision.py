"""A capability list counts its edits, so an approval can go stale (#640).

The owner's rule (2026-09-25): classifications stay editable until release,
every edit is audited, and step 3 must run again after any edit. The API already
let every step-2 edit through on an APPROVED list, but nothing recorded that
the list had moved since it was approved, so step 4 rendered the deliverable
from rows nobody re-approved.

- `revision`: incremented, in SQL, by every step-2 edit, in the same
  transaction as that edit's audit row.
- `approved_revision`: set to `revision` by the approve compare-and-swap.
- `deliverables.capability_list_revision`: the list revision a Tech Debt
  deliverable was rendered from, stamped at finalize. Release refuses a
  deliverable whose revision is not the list's `approved_revision`, so a
  document generated before an edit and a re-approval cannot reach the client.

The approval is current iff `approved_revision == revision`. A counter rather
than timestamps: an edit in the same clock tick as the approval cannot be
misread, and nothing depends on clocks.

## Backfill

`revision = 0` everywhere. `approved_revision = 0` for lists already APPROVED
or RELEASED, so they read as current: nothing on record says they were edited
after approval, and the counter did not exist to say so. That is a statement
about what was recorded, not a claim that no edit happened; the audit log is
where a pre-0056 edit would show. DRAFT and DISCARDED lists stay NULL, which
never equals a revision.

`deliverables.capability_list_revision` stays NULL for every existing row, and
release refuses NULL. Before #640 an approved list could already be edited, so
nothing on record says an older deliverable's rows are the approved ones:
missing data defaults to UNCONFIRMED, and the remedy is to generate the
deliverable again. Measured read-only on the shared dev database, 2026-09-26:
no Tech Debt deliverable was finalized and unreleased against an APPROVED list
(two released ones exist, and their lists are already RELEASED, where release
does not re-check the list). That is one developer database, not a deployment.

## Chain order

Migrations land in number order and are renumbered at landing if the order
changes (owner decision, 2026-09-25). This was first numbered 0055; #658 landed
first as 0055, so this is 0056 and chains from it.

SQLite-safe via `batch_alter_table` (core principle 6).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056"
down_revision: str | Sequence[str] | None = "0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("capability_lists") as batch:
        batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("approved_revision", sa.Integer(), nullable=True))
    with op.batch_alter_table("deliverables") as batch:
        batch.add_column(sa.Column("capability_list_revision", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE capability_lists SET approved_revision = 0 "
        "WHERE status IN ('APPROVED', 'RELEASED')"
    )


def downgrade() -> None:
    with op.batch_alter_table("deliverables") as batch:
        batch.drop_column("capability_list_revision")
    with op.batch_alter_table("capability_lists") as batch:
        batch.drop_column("approved_revision")
        batch.drop_column("revision")

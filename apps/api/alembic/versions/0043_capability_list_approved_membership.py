"""capability_lists.approved_membership — what the consultant actually approved

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-20 00:00:00

W3. Approving a Tech Debt capability list did not fix what was in it. Five doors
edit an APPROVED list — `patch_capability_item` (any field, including `name`),
add-components, `include_excluded_row`, and the security-classification confirm
queue — and `_editable_list_or_404` blocks only RELEASED and DISCARDED, so the
whole window between approval and release is mutable.

That matters because `attack.py::_client_tool_names` builds a HARD ALLOW-LIST
from those names: a tool missing from it cannot be cited, so the technique it
covers reads as uncovered — a fabricated gap, an absence the report presents as
assessed. The confirm queue makes this a *sanctioned* post-approval change of
allow-list membership: confirming a tool non-security after an ATT&CK run leaves
its "confirmed" citations checked against a list that no longer contains it.

So this column records the membership as it stood at the moment of approval:
`[{"item_id": ..., "name": ...}]` for every item then in security scope. It is
what "approved" has to mean before W2's narrow-confirmed can rest on it.

Additive and nullable (the C0 pattern): lists approved before this migration
have NULL and keep reading live rows, because inventing a snapshot for them
would assert a membership nobody recorded. Re-approving refreshes it, which is
the deliberate escape hatch — the workflow is not blocked, the change is just
made explicit and audited.

JSON rather than an association table: it is a frozen historical record, never
joined or filtered on, and a table would invite exactly the mutation this exists
to prevent.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # batch_alter_table: tests run SQLite, prod runs Postgres.
    with op.batch_alter_table("capability_lists") as batch:
        batch.add_column(sa.Column("approved_membership", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("capability_lists") as batch:
        batch.drop_column("approved_membership")

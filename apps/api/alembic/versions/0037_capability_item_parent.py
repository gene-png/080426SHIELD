"""capability_items.parent_item_id — decompose a bundled licence into components

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-05 00:00:00

Adds a nullable self-referential ``parent_item_id`` so one uploaded row can
expand into the capabilities it actually contains.

Motivation (2026-08-04 guided review). "Microsoft 365 E5" extracted as a single
$294,120 line. E5 contains Defender for Endpoint, Defender for Office 365,
Entra ID P2, Intune and Purview, and the same client separately licenses
CrowdStrike, Proofpoint and Okta — so three of the five redundancies planted in
the test inventory were undetectable, because the overlapping halves were
invisible. Asked directly whether it decomposes bundles, the platform did not:
the components must be named.

Deliberately NOT inferred by the model. A consultant names the components
during review; the AI is never asked "what is in this bundle?", which would be
exactly the fabricated-detail failure the redaction/AI seam exists to avoid.

Cost accounting: a component carries NO cost of its own. The parent keeps the
whole licence value, so decomposing a bundle can never inflate the portfolio
total — it only makes the capabilities inside it visible to redundancy analysis
and to the ATT&CK tool mapping (which reads capability names for the client).

Wholly additive (C0 pattern): nullable, so every existing row parses unchanged
as a top-level capability. SQLite-safe via ``batch_alter_table`` (tests run
SQLite, prod runs Postgres). The FK is created inside the batch block so SQLite
rebuilds the table with it rather than rejecting an ALTER.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | Sequence[str] | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("capability_items") as batch:
        batch.add_column(sa.Column("parent_item_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_capability_items_parent_item_id",
            "capability_items",
            ["parent_item_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("capability_items") as batch:
        batch.drop_constraint("fk_capability_items_parent_item_id", type_="foreignkey")
        batch.drop_column("parent_item_id")

"""capability_lists reconciliation — how many uploaded rows were excluded

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-05 00:00:00

Adds ``source_rows_total`` and ``excluded_rows`` to ``capability_lists`` so an
extraction can state what it left out.

Motivation (2026-08-04 guided review). A 21-row inventory totalling $1,634,236
produced 12 capabilities totalling $891,796. Nine non-security rows were
dropped, which is exactly what the extraction prompt asks for — but the
workspace reported "CAPABILITIES 12 · ANNUAL COST $891,796" with no indication
that 45% of the uploaded spend was missing. A consultant reading that has no way
to know the inventory is partial.

The counts are computed in code from the ``source_row_index`` each extracted
item already carries (``app/tech_debt/reconcile.py``); the model is never asked
how much it dropped. They are persisted because the workspace re-fetches the
list on every load, and a disclosure that vanishes on refresh is no disclosure.

``excluded_rows`` is JSON: a list of ``{index, summary}`` so the UI can show
WHICH rows were left out, not merely how many. Empty when the provider did not
attribute every item to a source row — the count stays honest, the naming is
withheld rather than guessed.

Wholly additive (C0 pattern): both columns are nullable, so every pre-migration
list parses unchanged as "reconciliation unknown" and renders no claim.
SQLite-safe via ``batch_alter_table`` (tests run SQLite, prod runs Postgres).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | Sequence[str] | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("capability_lists") as batch:
        batch.add_column(sa.Column("source_rows_total", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("excluded_rows", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("capability_lists") as batch:
        batch.drop_column("excluded_rows")
        batch.drop_column("source_rows_total")

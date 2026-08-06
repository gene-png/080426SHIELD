"""capability_items security classification — portfolio scope for Tech Debt

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-05 00:00:00

Tech Debt now covers the WHOLE software portfolio, not only security tooling.
Previously the extraction prompt kept security capabilities and silently dropped
everything else: the 2026-08-04 guided review uploaded 21 rows / $1,634,236 and
the workspace showed 12 items / $891,796, presenting the survivors as the entire
inventory. Broadening the scope means every row becomes a capability, and the
security question moves from "was it kept?" to "how is it classified?".

Three additive columns carry that classification:

``security_related``
    Tri-state on purpose. NULL means "not classified" — every row written before
    this migration, which must not be silently read as a negative. True/False is
    the model's call.

``security_functions``
    JSON list drawn from prevent / detect / respond. A LIST, not a scalar:
    CrowdStrike Falcon genuinely serves all three, and the three map one-to-one
    onto the columns ATT&CK coverage already keeps
    (``prevention_tools`` / ``detection_tools`` / ``response_tools``).

``security_class_confirmed``
    A consultant has signed off on a NEGATIVE classification.

Why the sign-off exists. ``_client_tool_names`` feeds the ATT&CK mapping, and
that list is not merely input — it is a hard allow-list on which tools the model
may cite (routes/attack.py). A tool wrongly marked non-security therefore
becomes *uncitable*, opening a coverage blind spot that reads as an assessed
absence rather than a missing input. So an UNCONFIRMED negative is not acted on:
the row stays in the ATT&CK subset until a human agrees it does not belong.
Failing toward a needless second look is the cheap direction; failing toward a
silent blind spot is not.

Wholly additive (C0 pattern): all three nullable or defaulted, so pre-0038 rows
parse unchanged. SQLite-safe via ``batch_alter_table`` (tests run SQLite, prod
runs Postgres).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: str | Sequence[str] | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("capability_items") as batch:
        batch.add_column(sa.Column("security_related", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("security_functions", sa.JSON(), nullable=True))
        batch.add_column(
            sa.Column(
                "security_class_confirmed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("capability_items") as batch:
        batch.drop_column("security_class_confirmed")
        batch.drop_column("security_functions")
        batch.drop_column("security_related")

"""CSF Working Profile evidence, three values (Options 1 and 3).

Revision ID: 0074
Revises: 0072

Gene, #736 6201691989 item 2: the "Evidence on file" box becomes three
values, `on_file` / `confirmed_in_discussion` / `neither`, so a level the
consultant confirmed in discussion is told apart from one nobody confirmed.
The boolean cannot hold the middle value, hence this migration.

On `csf_dimension_scores`:

- adds `evidence_status`, VARCHAR(32) NOT NULL, server default `'neither'`;
- backfills it from `has_evidence`: true is `on_file`, false is `neither`
  (6201691989: "existing true reads as Evidence on file, false as Neither");
- drops `has_evidence`. One stored statement of the fact, not two kept in
  step; the model derives `has_evidence` (`== on_file`) for its readers.

`batch_alter_table`, so it runs on SQLite (tests) and Postgres alike.

## Blast radius, measured before choosing

Read-only on the dev database (alembic 0072, 2026-10-15,
`BEGIN TRANSACTION READ ONLY` through `docker exec shield-v2-db-1 psql`):
530 rows across one RELEASED, one APPROVED and one SUBMITTED assessment, none
with `has_evidence` true. Every row becomes `neither`. No score or level is
read differently: the backfill maps the boolean onto the value that means
the same, and the frozen cap reads `on_file` exactly as it read true.

## Downgrade

Maps `on_file` back to true and the other two to false, and REFUSES, naming
the count, when either of these exists, because the old schema or code
cannot hold it:

- a `confirmed_in_discussion` row: false would erase what the consultant
  recorded;
- a CSF assessment with `rollup_rules = 3` (approved under Options 1 and 3,
  `app/csf/rules.py`): code before this change raises on 3, and rewriting it
  to 2 would cap levels that were delivered uncapped.

On an empty database neither exists, so a test rewinding past 0074 is not
refused.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0074"
down_revision: str | Sequence[str] | None = "0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("csf_dimension_scores") as batch:
        batch.add_column(
            sa.Column(
                "evidence_status",
                sa.String(32),
                nullable=False,
                server_default=sa.text("'neither'"),
            )
        )
    op.execute(
        sa.text(
            "UPDATE csf_dimension_scores SET evidence_status = "
            "CASE WHEN has_evidence THEN 'on_file' ELSE 'neither' END"
        )
    )
    with op.batch_alter_table("csf_dimension_scores") as batch:
        batch.drop_column("has_evidence")


def _count(sql: str) -> int:
    return op.get_bind().execute(sa.text(sql)).scalar_one()


def downgrade() -> None:
    confirmed = _count(
        "SELECT COUNT(*) FROM csf_dimension_scores "
        "WHERE evidence_status = 'confirmed_in_discussion'"
    )
    if confirmed:
        raise RuntimeError(
            f"Refusing to downgrade 0074: {confirmed} CSF Working Profile row(s) record "
            "evidence as confirmed in discussion, which the boolean has_evidence cannot "
            "hold; downgrading would erase it."
        )
    uncapped = _count("SELECT COUNT(*) FROM csf_assessments WHERE rollup_rules = 3")
    if uncapped:
        raise RuntimeError(
            f"Refusing to downgrade 0074: {uncapped} CSF assessment(s) have "
            "rollup_rules = 3 (approved with no evidence cap). Code before 0074 cannot "
            "read 3, and rewriting it to 2 would cap levels that were delivered uncapped."
        )
    with op.batch_alter_table("csf_dimension_scores") as batch:
        batch.add_column(
            sa.Column("has_evidence", sa.Boolean, nullable=False, server_default=sa.false())
        )
    op.execute(
        sa.text(
            "UPDATE csf_dimension_scores SET has_evidence = "
            "CASE WHEN evidence_status = 'on_file' THEN TRUE ELSE FALSE END"
        )
    )
    with op.batch_alter_table("csf_dimension_scores") as batch:
        batch.drop_column("evidence_status")

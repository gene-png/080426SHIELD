"""Record which rule set an ATT&CK assessment was approved under (#620, D-094).

Gene's condition on #620, 2026-09-25: **a released assessment keeps rendering
what was delivered.** #620 changes how a computed parent is presented -- the
triad population, its own tools and rationale, the matrix row, the blind-spot
cards, the Risk Register findings, and a pending-review derivation that is
computed on every read. Those rules may apply only to assessments approved
after #620, so a live dashboard never contradicts a delivered PDF or XLSX.

## The column

`attack_assessments.parent_rules`, nullable, additive:

* `1` -- approved before #620: render the old rules.
* `2` -- approved under D-094: render the new rules. Written at approve.
* NULL -- a draft, not yet approved: the NEW rules (Gene's addition 1).

`app/attack/rules.py::parents_computed` is the only reader, and it raises on
any other value rather than defaulting to either rule.

## The backfill is HERE, not in application code

Every assessment already APPROVED or RELEASED was delivered, or is about to
be, under the old rules, so it gets `1`. The status column stores the enum's
NAME (`APPROVED`, `RELEASED`), measured on the dev database on 2026-09-25 --
matching on the lowercase VALUE would update no row and look fine doing it.
DRAFT and DISCARDED rows stay NULL: a draft takes its value when approved, and
a discarded draft is never read by a client surface.

## Chains from 0052, which is the head

The chain's order is not the number order: on `main` it runs 0051 -> 0053 ->
0052, so the head is 0052. `tests/unit/test_alembic_single_head.py` fails on
a forked or broken chain.

SQLite-safe via `batch_alter_table` (core principle 6).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054"
down_revision: str | Sequence[str] | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("attack_assessments") as batch:
        batch.add_column(sa.Column("parent_rules", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE attack_assessments SET parent_rules = 1 WHERE status IN ('APPROVED', 'RELEASED')"
    )


def downgrade() -> None:
    # REFUSED while any assessment was approved under D-094 (#620 round 4). The
    # column cannot be dropped without losing which rule set each one was
    # approved under, and re-running `upgrade` would then backfill every
    # APPROVED and RELEASED row to 1 -- silently moving a rule-2 release onto
    # the old rules. A downgrade that loses that fact is not a downgrade.
    bind = op.get_bind()
    count = bind.execute(
        sa.text("SELECT COUNT(*) FROM attack_assessments WHERE parent_rules = 2")
    ).scalar_one()
    if count:
        raise RuntimeError(
            f"Refusing to downgrade 0054: {count} ATT&CK assessment(s) have "
            "parent_rules = 2 (approved under D-094). Dropping the column would lose "
            "that, and re-upgrading would backfill them to the old rules (1)."
        )
    with op.batch_alter_table("attack_assessments") as batch:
        batch.drop_column("parent_rules")

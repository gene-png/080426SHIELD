"""Where an item's annual cost came from, on `capability_items` (TD-5, for #1060).

Revision ID: 0074
Revises: 0076

The number 0074 is the advisor's (#736 6206818759, item 5). Its parent was
main's single head when written, 0072; CSF's 0075 (#1203) landed first with the
same parent, and ZT's 0076 (#1347) then chained after 0075. By the advisor's
ruling (#736 issuecomment-6225076633) 0074 chains after 0076, main's head when
this PR merged main (`test_alembic_single_head` reads the chain, never
filenames).

Two nullable columns:

- `cost_source`: `ai_estimate` when the opt-in AI cost estimate wrote the cost,
  `consultant` when a consultant edited it afterwards (the override). NULL means
  not recorded: every upload-extracted cost and every existing row. NULL is
  NEVER read as an estimate. A CHECK holds the vocabulary.
- `cost_estimate_basis`: the model's one-sentence basis for an estimate, shown
  to the consultant only. Cleared when a consultant overrides the cost.

## Blast radius

Additive and nullable; nothing is backfilled. Every existing row keeps NULL in
both columns, which reads as "not an estimate", exactly what those costs are.
No figure moves until a consultant runs the estimate.

## The downgrade refuses while any row holds a value 0074 added

Dropping `cost_source` would leave an AI estimate in `annual_cost_usd` with
nothing saying it is one, and every surface would then present it as a cost
the client provided. On a database with estimates the downgrade is, in
practice, one-way until someone clears them deliberately.

## Clearing before a downgrade

Only once someone has decided the data may go. An AI-estimated cost must not
survive its label, so this clears the estimated costs too:

    UPDATE capability_items SET annual_cost_usd = NULL WHERE cost_source = 'ai_estimate'
    UPDATE capability_items SET cost_source = NULL, cost_estimate_basis = NULL

then `alembic downgrade 0076`.

That first statement matches every list's rows, RELEASED ones included, so a
released deliverable's re-export would then show those tools with no cost.
The downgrade itself clears nothing; a person runs these.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql.elements import conv

revision: str = "0074"
down_revision: str | Sequence[str] | None = "0076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The two recorded sources. NULL (not recorded) is the third state.
_SOURCES = ("ai_estimate", "consultant")
_VOCABULARY = "cost_source IS NULL OR cost_source IN ({})".format(
    ", ".join(f"'{s}'" for s in _SOURCES)
)
_CK_VOCABULARY = "ck_capability_items_cost_source_vocabulary"

_COLUMNS = ("cost_source", "cost_estimate_basis")
_HELD = "SELECT COUNT(*) FROM capability_items WHERE " + " OR ".join(  # nosec B608
    f"{c} IS NOT NULL" for c in _COLUMNS
)
_CLEAR = (
    "UPDATE capability_items SET annual_cost_usd = NULL WHERE cost_source = 'ai_estimate'; "
    "UPDATE capability_items SET cost_source = NULL, cost_estimate_basis = NULL"
)


def upgrade() -> None:
    with op.batch_alter_table("capability_items") as batch:
        batch.add_column(sa.Column("cost_source", sa.String(16), nullable=True))
        batch.add_column(sa.Column("cost_estimate_basis", sa.Text(), nullable=True))
        batch.create_check_constraint(conv(_CK_VOCABULARY), _VOCABULARY)
    print("[0074] added to capability_items, all NULL on existing rows: " + ", ".join(_COLUMNS))


def downgrade() -> None:
    held = op.get_bind().execute(sa.text(_HELD)).scalar_one()
    if held:
        noun = "capability item holds" if held == 1 else "capability items hold"
        raise RuntimeError(
            f"Refusing to downgrade 0074: {held} {noun} a cost source or an AI "
            "estimate's basis. Dropping them would leave an AI-estimated cost "
            "presented as a provided one, and a re-upgrade restores NULL, not the "
            "label. To clear them deliberately, once the data may go, run: "
            f"{_CLEAR}."
        )
    with op.batch_alter_table("capability_items") as batch:
        batch.drop_constraint(conv(_CK_VOCABULARY), type_="check")
        for column in reversed(_COLUMNS):
            batch.drop_column(column)

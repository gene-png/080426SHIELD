"""Record the model-supplied links a risk entry LOST (#132)

Revision ID: 0048
Revises: 0047
Create Date: 2026-09-11 00:00:00

`routes/risk.py` filtered the model's proposed links against the client's own
assessments with a bare comprehension::

    techs = [t for t in (raw.get("linked_techniques") or []) if t in valid_techniques]
    controls = [c for c in (raw.get("linked_controls") or []) if c in valid_controls]

Every non-matching entry was discarded with no counter, no reason and no
example -- nothing in the audit row, nothing in the response, nothing in a log
line. That is `_validate_tools` as it looked before the ATT&CK work rewrote it,
surviving in a REIMPLEMENTATION: `risk.py` never calls the ATT&CK resolver, so
a complete call-site sweep reported clean over it.

## Why a column rather than a counter

A counter on the generate response describes a RUN. The harm outlives the run.

A risk entry whose every technique link was dropped is persisted with
`linked_techniques = []`, which is byte-identical to an entry the model linked
nothing for. The consultant opens the register a week later and reads "the AI
found no ATT&CK relevance" when the truth may be "the AI proposed five
techniques and all five were misspelled". Those are different facts and they
were the same stored bytes.

This is #102's finding, reached from a different direction, and #102 already
decided it: outcomes that resolve to NOTHING get persisted rows of their own,
"because otherwise 'we dropped the model's evidence' and 'nobody ever cited
anything' are the same stored bytes."

## What pre-migration rows get: NULL, and NULL means "not recorded"

Not `{}`. `{}` is a positive claim -- "the model proposed nothing that did not
resolve" -- and no SQL recovers whether that is true of a register generated
last month. Writing it would put a clean bill of health into the column whose
only purpose is recording what happened.

`CLAUDE.md`: **missing data defaults to UNCONFIRMED, never to confirmed.** Same
call 0047 made one table over, for the same reason.

The three states the route relies on, and they are three rather than two:

  * ``NULL``  -- pre-0048 row. Nothing was recorded; nothing may be inferred.
  * ``{}``    -- recorded, and nothing was dropped. A real clean bill.
  * ``{"linked_techniques": [...], ...}`` -- what the model offered and lost.

## TO WHOEVER WRITES THE NEXT MIGRATION THAT TOUCHES THIS COLUMN

Do not backfill it. The NULL is load-bearing: the serializer branches on it and
reports "not recorded" rather than "none", and collapsing that distinction
reinstates the defect this column exists to end.

SQLite-safe via `batch_alter_table`, and additive/optional so older rows parse
unchanged (the C0 pattern).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("risk_entries") as batch_op:
        batch_op.add_column(
            sa.Column(
                "dropped_links",
                sa.JSON(),
                nullable=True,
                # No server_default ON PURPOSE -- see the module docstring. `{}`
                # would assert "nothing was dropped" for every row written
                # before anyone was counting.
                comment=(
                    "Model-supplied link values that matched nothing in the "
                    "client's own assessments and were discarded, keyed by "
                    "field. `{}` means nothing was dropped; NULL means not "
                    "recorded (pre-0048 rows)."
                ),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("risk_entries") as batch_op:
        batch_op.drop_column("dropped_links")

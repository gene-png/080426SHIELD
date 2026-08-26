"""Record the redaction mode on each `llm_calls` row (#144)

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-25 00:00:00

`app/ai/redact.py` is the primary compensating control for egress to a
commercial, non-FedRAMP provider, and the audit row's stated job -- in
`docs/security.md` and in Master Spec 12 -- is to prove it ran.

It could not. With `SHIELD_REDACTION_MODE=off` the redactor returns the input
unchanged and `redacted_counts` is stored as NULL, which is byte-identical to a
run where the redactor executed and found nothing to remove. `llm_calls.mode` is
the `LLMCallMode` enum -- fixture vs live -- not the redaction mode. Nothing on
the row distinguished the two states.

#142 closed the way the bad configuration could be selected outside development.
This closes the evidence gap, which #142 cannot: prevention does not answer
"did it happen before?" for a row already written.

## The load-bearing decision: what pre-migration rows get

**They stay NULL, and NULL means "not recorded".**

Every row written before this migration has an unknown redaction mode. The
information was never captured, and no amount of SQL recovers it. Backfilling
`'strict'` because that is the default would write a value the database cannot
know into the column whose entire purpose is proving what actually happened --
a fabricated record in the audit table, on a platform targeting FedRAMP
Moderate/High. That is worse than the NULL it replaces, because a NULL is
visibly absent and a fabricated `'strict'` is not.

CLAUDE.md states the general form: **missing data defaults to UNCONFIRMED, never
to confirmed.** Absence of evidence is not evidence of confirmation.

Same call as #114 one table over, and #59 is the standing evidence for why the
silent-fallback version is the trap.

## Measured, not assumed

* The dev database holds **0** `llm_calls` rows, so nothing is grandfathered here
  in practice. There is no production deployment.
* **No read path aggregates on this column.** The only consumer of `llm_calls` is
  the keyset-paginated admin list (`app/routes/admin.py`), which projects rows
  through `AdminLlmCallRow` and neither groups, filters nor sums. A NULL
  therefore renders as "not recorded" rather than silently dropping the row from
  a count -- the shape that made the excluded-rows disclosure vanish.

## Shape

Additive, nullable, **no server-side default** (the C0 pattern). A DB default
would manufacture exactly the value this migration declines to manufacture, and
would do it for every future row whose writer forgot to set it.

`batch_alter_table` for SQLite safety: tests run SQLite, prod runs Postgres.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("llm_calls") as batch_op:
        batch_op.add_column(
            sa.Column(
                "redaction_mode",
                sa.String(length=16),
                nullable=True,
                # No server_default ON PURPOSE. See the module docstring: a
                # default would fabricate the value for pre-migration rows and
                # for any future writer that forgets to set it.
                comment=(
                    "strict|standard|off, as resolved for this call. "
                    "NULL means the mode was not recorded (pre-0046 rows)."
                ),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("llm_calls") as batch_op:
        batch_op.drop_column("redaction_mode")

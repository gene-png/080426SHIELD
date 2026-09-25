"""Store why an ATT&CK status was chosen: a reason code and a narrative (#554).

The owner decided the ATT&CK status vocabulary on 2026-09-24 (#554). Partial
carries one of seven reason codes. N/A carries `platform_absent`.
`outside_control_surface` carries which surface the client cannot reach. And
`unable_to_determine` carries a narrative of what could not be verified. The
statuses themselves need no migration: `attack_coverage.status` is a free
String(32).

## Both columns are nullable, and existing rows stay NULL

A NULL reason means "none given". Whether a row may ship without one is decided
at release, not in storage ("gate the release, not the click", #557). Existing
rows are left NULL rather than guessed: nothing recorded why they were scored as
they were.

## Chains from 0051, and that is a known merge-order point

`0052` (`attack_assessments.catalog_version`) lives on the open #556 catalog PR
(#562), not on main. This migration was cut from main, so it chains from `0051`. Once
either PR merges, the other's `down_revision` must be re-pointed to keep a
single head. The owner tests every PR pair before merging; this note is there
so the fix is not rediscovered as a red CI run.

SQLite-safe via `batch_alter_table` (core principle 6); additive and nullable.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053"
down_revision: str | Sequence[str] | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("attack_coverage") as batch:
        batch.add_column(sa.Column("reason_code", sa.String(length=48), nullable=True))
        batch.add_column(sa.Column("narrative", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("attack_coverage") as batch:
        batch.drop_column("narrative")
        batch.drop_column("reason_code")

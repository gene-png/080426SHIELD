"""Record when a user's credentials last changed, so older access tokens are refused (#658).

A password reset ended every refresh family (#633) but left an ACCESS token
issued before it valid until its own TTL. `current_user` now refuses a token
whose `iat` predates this cutoff. The owner's rule, 2026-09-25: the value is
truncated to whole seconds, and a token is accepted iff `iat >= cutoff`.

## Existing rows stay NULL, deliberately

NULL means no cutoff: no credential change has been recorded since this column
existed, so no token is refused by it. That is the true state of every existing
row. Backfilling "now" would sign every user out at deploy, for a change nobody
made.

## Chain order: written after 0052, numbered 0056

Migrations land in number order (owner decision, 2026-09-25): #620 lands 0054,
#640 lands 0055, and this one 0056. #620 is on `main`; 0055 is not, so this
revision chains from `main`'s head, 0054, to keep a single head here. If 0055
lands first, `down_revision` becomes 0055 at landing.

SQLite-safe via `batch_alter_table` (core principle 6); additive and nullable,
so older code reading a newer database is unaffected.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056"
down_revision: str | Sequence[str] | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("credentials_changed_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("credentials_changed_at")

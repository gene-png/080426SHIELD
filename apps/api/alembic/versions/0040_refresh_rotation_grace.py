"""refresh-rotation grace — stop concurrent requests logging a user out

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-08 00:00:00

Refresh tokens are single-use: each ``/auth/refresh`` mints a new one and
overwrites ``users.active_refresh_jti``, so a replayed token no longer matches
and is rejected. That is the right control, and it had a failure mode nobody
designed for.

A browser routinely fires several requests at once when the access token
expires, and every one of them presents the SAME refresh token. The first
rotates it; the rest are rejected as replay. The web treats that rejection as
terminal, so the user is signed out mid-task. Observed in the API log as pairs
of ``auth.refresh_reused`` **286 microseconds apart** — 13 of them in three
hours, each one a hard bounce to /sign-in.

These two columns let the immediately-previous jti stay acceptable for a short
window (``jwt_refresh_grace_seconds``, default 60). Within it the CURRENT pair
is re-issued rather than rotated again, so concurrent callers converge on one
token identity instead of knocking each other out.

The security envelope is deliberately narrow: only the IMMEDIATELY previous jti
is remembered (not a history), and only for the window. A token two generations
old, or replayed after the window, is rejected exactly as before.

Wholly additive (C0 pattern), SQLite-safe via ``batch_alter_table`` (tests run
SQLite, prod runs Postgres). NULL means "no rotation has happened yet", which is
what every existing row means.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: str | Sequence[str] | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("previous_refresh_jti", sa.String(36), nullable=True))
        batch.add_column(sa.Column("refresh_rotated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("refresh_rotated_at")
        batch.drop_column("previous_refresh_jti")

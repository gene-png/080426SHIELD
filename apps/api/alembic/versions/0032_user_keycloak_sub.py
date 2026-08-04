"""users.keycloak_sub for the hybrid OIDC exchange (Sprint 9 T4, D-032)

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-21 00:00:00

Adds a nullable, UNIQUE ``keycloak_sub`` column to ``users``. The hybrid OIDC
exchange (POST /auth/oidc/exchange) TOFU-binds the Keycloak subject on a user's
first SSO login and rejects a later exchange whose subject differs. Wholly
additive (C0 pattern): the column is nullable so pre-migration rows and
pure-credentials users parse unchanged as "never bound". UNIQUE permits many
NULLs (both Postgres and SQLite), and prevents two local accounts from binding
the same Keycloak identity. SQLite-safe via ``batch_alter_table``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | Sequence[str] | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("keycloak_sub", sa.String(length=64), nullable=True))
        batch.create_unique_constraint("uq_users_keycloak_sub", ["keycloak_sub"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_keycloak_sub", type_="unique")
        batch.drop_column("keycloak_sub")

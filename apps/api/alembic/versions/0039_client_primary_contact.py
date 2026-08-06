"""client primary-contact override — "I am not the primary contact"

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-06 00:00:00

Intake collects the contact from the signed-in user's own record
(``display_name`` / ``title`` / ``phone`` on ``users``). That is right when the
person filling in the wizard is the engagement's point of contact, and wrong
whenever they are not — an assistant, a procurement lead, or anyone completing
the form on someone else's behalf. Today they have no way to say so, and the
email field is deliberately read-only, so the intake records the wrong POC and a
consultant contacts the wrong person (UX finding 9).

Four nullable columns on ``client``, because the primary contact belongs to the
engagement rather than to whichever account happened to type it in. NULL means
"the contact is the submitting user", which is what every existing row means and
what the wizard still defaults to — so nothing changes for anyone who is the
contact.

No new endpoint: these ride the existing ``ClientProfilePatch`` auto-save path
that the rest of the Organization step already uses.

Wholly additive (C0 pattern), SQLite-safe via ``batch_alter_table`` (tests run
SQLite, prod runs Postgres).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: str | Sequence[str] | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("client") as batch:
        batch.add_column(sa.Column("primary_contact_name", sa.String(255), nullable=True))
        batch.add_column(sa.Column("primary_contact_email", sa.String(320), nullable=True))
        batch.add_column(sa.Column("primary_contact_title", sa.String(255), nullable=True))
        batch.add_column(sa.Column("primary_contact_phone", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("client") as batch:
        batch.drop_column("primary_contact_phone")
        batch.drop_column("primary_contact_title")
        batch.drop_column("primary_contact_email")
        batch.drop_column("primary_contact_name")

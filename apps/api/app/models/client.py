"""Client - a tenant (organization) served by this deployment.

Originally Master Spec §11 was single-tenant (one client row per deployment).
Migration 0013 turned this into a multi-tenant model: many clients per
deployment, every business row tagged with its `client_id`. Platform
admin users have `User.client_id = NULL` and can switch between clients
via the X-Client-Id request header; client-role users are pinned to
their `User.client_id`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin


class Client(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "client"

    # NULL means NOBODY HAS NAMED THIS ORGANISATION YET (D-080, #254). It is not
    # "unknown" and not a placeholder: it is the record that no name was offered.
    #
    # Only a HUMAN NAMING AN ORG may write it. Two paths qualify -- an admin
    # typing a name in `routes/admin.py`, and the client typing one through the
    # intake wizard -- and `routes/auth.py` self-serve provisioning does not,
    # because a registration form collects a person and an email address and
    # neither is the name of a company. It leaves this column NULL.
    #
    # That is the RULE. For the actual writer set, run the predicate rather than
    # trusting a list here, because the list was written out twice and was wrong
    # both times (it missed `scripts/seed_demo.py`):
    #
    #     grep -rn "legal_name\s*=" --include=*.py apps/api scripts | grep -v ==
    #
    # Every writer that takes user input normalises before it lands, so a name
    # stored FROM D-080 ONWARD is NULL or non-empty and trimmed. That is a
    # write-time invariant and it does not reach backwards: `ClientProfilePatch`
    # has no validator, so a pre-D-080 `PATCH /intake` could store `"   "`, and
    # migration 0049 does not NULL it (its predicates match a domain, a display
    # name, or the old sentinel -- not whitespace). Read-side guards therefore
    # still `.strip()`; an invariant enforced at every writer says nothing about
    # rows that predate the enforcement.
    #
    # The column is the condition. Every guard that needs "has this org been
    # named" tests `legal_name` itself rather than a sentinel string or a second
    # flag, because a second representation is one that can disagree with this
    # one -- and the sentinel this replaced was read in 13 places and written in
    # none, so every one of those guards was dead.
    #
    # NOT keyed on `intake_completed_at`: an admin-created tenant has a real name
    # and never completes intake, so an intake-keyed guard would blank its
    # deliverables and refuse its engagements.
    legal_name: Mapped[str | None] = mapped_column(String(255))
    dba_name: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(512))
    size_band: Mapped[str | None] = mapped_column(String(64))
    industry: Mapped[str | None] = mapped_column(String(128))

    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(64))
    postal_code: Mapped[str | None] = mapped_column(String(32))
    country: Mapped[str | None] = mapped_column(String(64))

    primary_poc_user_id: Mapped[uuid.UUID | None] = mapped_column()
    prompting_context: Mapped[str | None] = mapped_column(Text)

    # service_interests is a list-of-codes set at intake time. Stored as a
    # JSON array on SQLite for tests; native ARRAY(text) on Postgres.
    service_interests: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(32)).with_variant(JSONB, "sqlite")
    )

    # Master Spec §11: set when the intake wizard is submitted. Used by the
    # admin queue to surface new leads.
    intake_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Issue 3: set by DELETE /admin/clients/{cid}. An archived tenant drops out
    # of the platform client list and the intake queue org index but keeps every
    # row it owns — removal is reversible and never destroys the audit trail.
    # NULL means active (the C0 additive pattern: pre-migration rows parse
    # unchanged).
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Primary-contact override (migration 0039). NULL means "the contact is the
    # user who submitted the intake", which is what every pre-0039 row means.
    # Set only when whoever filled in the wizard says they are NOT the point of
    # contact — an assistant or procurement lead completing it for someone else.
    # The contact belongs to the engagement, not to the account that typed it.
    primary_contact_name: Mapped[str | None] = mapped_column(String(255))
    primary_contact_email: Mapped[str | None] = mapped_column(String(320))
    primary_contact_title: Mapped[str | None] = mapped_column(String(255))
    primary_contact_phone: Mapped[str | None] = mapped_column(String(64))

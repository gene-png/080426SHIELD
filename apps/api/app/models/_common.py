"""Mixins and helpers shared across models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, text
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    """Always-UTC current time (Master Spec §11.2: store UTC, render local)."""
    return datetime.now(UTC)


class UUIDPKMixin:
    """UUID primary key, generated client-side so we can audit-log a create
    without an extra round-trip."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


def one_draft_index(table: str) -> Index:
    """#1120 (migration 0073): at most one DRAFT per service, in the database.

    Both dialect clauses, as `uq_ai_runs_one_running` carries them: an index
    declared with only one is a plain UNIQUE index on the other dialect, which
    would refuse a second record EVER. `'DRAFT'` is the member NAME that
    `native_enum=False` stores."""
    return Index(
        f"uq_{table}_one_draft",
        "service_id",
        unique=True,
        sqlite_where=text("status = 'DRAFT'"),
        postgresql_where=text("status = 'DRAFT'"),
    )

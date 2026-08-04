"""Audit entry - append-only record of every state-changing action.

Master Spec §11: audit_entries (id, at, actor_user_id, action, target_type,
target_id, details jsonb, correlation_id). Append-only at three layers:
  1. The DB has a Postgres trigger forbidding UPDATE/DELETE
     (Phase 1 stage 2 migration; pg dialect only).
  2. SQLAlchemy event listeners enforce the same invariant in Python so
     SQLite tests catch logic bugs that try to mutate audit rows.
  3. The audit() helper is the only blessed code path for inserts; routes
     never construct AuditEntry directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base
from app.models._common import UUIDPKMixin, utcnow


class AuditEntry(UUIDPKMixin, Base):
    __tablename__ = "audit_entries"
    __table_args__ = (
        Index("ix_audit_entries_at", "at"),
        Index("ix_audit_entries_target", "target_type", "target_id"),
        Index("ix_audit_entries_correlation", "correlation_id"),
    )

    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column()
    details: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSONB, "postgresql"))
    correlation_id: Mapped[str | None] = mapped_column(String(128))


class AuditEntryImmutableError(RuntimeError):
    """Raised when application code attempts to mutate or delete an audit row."""


@event.listens_for(Session, "before_flush")
def _block_audit_mutations(session: Session, _flush_context, _instances) -> None:
    """Application-layer enforcement of append-only.

    Catches the bug the spec warns about (Master Spec §11 + AI Prompt §4.5)
    even when running against SQLite or when the prod DB trigger is missing.
    """
    for instance in session.dirty:
        if isinstance(instance, AuditEntry):
            raise AuditEntryImmutableError("audit_entries rows cannot be updated")
    for instance in session.deleted:
        if isinstance(instance, AuditEntry):
            raise AuditEntryImmutableError("audit_entries rows cannot be deleted")

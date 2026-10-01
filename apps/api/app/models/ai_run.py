"""AI run - one row per Run-AI, however many provider calls it makes (#645).

A Run-AI used to be one HTTP request: the browser waited while the api called
the provider and applied the result. ATT&CK's mitre_map makes ~26 provider
calls per run and outlasts the request timeout, so the browser gave up while
the server carried on. A run is now started by a POST that returns 202 and
finished by a background job; this row is what the two share, and what the
workspace polls.

One `llm_calls` row records one provider call, so it cannot represent a run of
26. `llm_calls.ai_run_id` points each call at the run it belongs to.

`status` follows the `llm_calls` enum convention (`native_enum=False`, no
`values_callable`), so the STORED value is the member NAME: `RUNNING`, not
`running`. The partial unique index in migration 0057 is written against that
stored spelling.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin, utcnow
from app.models.llm_call import LLMCallMode


class AiRunStatus(enum.StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AiRun(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "ai_runs"
    __table_args__ = (
        # At most one RUNNING run per service and purpose. Both dialect clauses,
        # because CI runs SQLite and production runs Postgres: an index declared
        # with only one of them is a plain UNIQUE index on the other, which
        # would refuse a second run EVER, not a second concurrent one.
        Index(
            "uq_ai_runs_one_running",
            "service_id",
            "purpose",
            unique=True,
            sqlite_where=text("status = 'RUNNING'"),
            postgresql_where=text("status = 'RUNNING'"),
        ),
        Index("ix_ai_runs_service_purpose", "service_id", "purpose"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="CASCADE"), nullable=False
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AiRunStatus] = mapped_column(
        SAEnum(AiRunStatus, name="ai_run_status", native_enum=False, length=16),
        default=AiRunStatus.RUNNING,
        nullable=False,
    )
    # What the provider built at POST time serves: FIXTURE is "offline", LIVE is
    # "live". A second POST joins this run only when it acknowledged the same.
    mode: Mapped[LLMCallMode] = mapped_column(
        SAEnum(LLMCallMode, name="ai_run_mode", native_enum=False, length=16),
        nullable=False,
    )
    # The api process that started the run. A RUNNING run from another boot can
    # have no job behind it (see `app/ai/runs.py`, the reaper).
    boot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    batches_total: Mapped[int | None] = mapped_column(Integer)
    batches_failed: Mapped[int | None] = mapped_column(Integer)
    applied_count: Mapped[int | None] = mapped_column(Integer)
    # Every disclosure the workspace renders about the run, so it survives a
    # reload (#271). Written in the same transaction as the apply.
    result: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSONB, "postgresql"))
    error_reason: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    # NULL is "not known", never "no": a crash outside the provider boundary
    # cannot say whether a call was billed.
    charged_likely: Mapped[bool | None] = mapped_column(Boolean)
    requested_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    # When the job gives up, and the edit lock with it. Shown on the workspace.
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

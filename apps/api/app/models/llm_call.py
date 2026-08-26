"""LLM call - one row per AI invocation.

Master Spec §11:
  llm_calls    id, service_id, purpose, prompt_version, model, mode
               (real/fixture), input_tokens, output_tokens, duration_ms,
               status (queued/running/completed/failed), error_message,
               response_artifact_id, requested_by, requested_at,
               completed_at.

The row is written BEFORE the provider call (status=running) so a crash
during the call still leaves a record. `redacted_counts` is JSON: counts
only (`{"email": 2, "phone": 1, ...}`), never payload content.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import get_args

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.redact import RedactionMode
from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin, utcnow


class LLMCallStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class LLMCallMode(enum.StrEnum):
    FIXTURE = "fixture"
    LIVE = "live"


class LLMCall(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "llm_calls"

    service_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL")
    )
    # Tenant attribution (Sprint 3 T5). Additive + nullable (C0): older rows and
    # calls made without a client carry NULL. SET NULL so deleting a client does
    # not erase the egress record — the audit row outlives the tenant.
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("client.id", ondelete="SET NULL")
    )
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[LLMCallMode] = mapped_column(
        SAEnum(LLMCallMode, name="llm_call_mode", native_enum=False, length=16),
        nullable=False,
    )

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[LLMCallStatus] = mapped_column(
        SAEnum(LLMCallStatus, name="llm_call_status", native_enum=False, length=16),
        default=LLMCallStatus.RUNNING,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    response_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )

    requested_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Counts of items removed by the redactor for this call's input.
    # Counts only - never payload content (Master Spec §12.1).
    # The redaction mode this call actually ran under (#144). WRITE-ONCE, set at
    # INSERT rather than at finalisation: the mode is known before the provider
    # is called, and a call that fails or is killed is exactly when "what was
    # egressed" matters most. Unlike `status`, `input_tokens` and `duration_ms`
    # on this row, nothing updates it after the insert.
    #
    # NULL means NOT RECORDED, never "strict". Rows written before migration 0046
    # have an unknown mode and no default is applied to them -- fabricating one
    # in the table whose job is proving what happened would be worse than the
    # absence. See the 0046 docstring.
    #
    # The domain comes from `RedactionMode` via `get_args` rather than a string
    # list repeated here: `app/ai/redact.py` stays the single source, so a
    # fourth mode is added in one place.
    #
    # `native_enum=False` + the default `create_constraint=False` emit plain
    # VARCHAR(16) -- byte-identical DDL to the `String(16)` this replaces, on
    # both Postgres and SQLite (measured on both dialects), so this needs no
    # migration and a fourth mode will not either. That is deliberate: Sprint 9
    # added a status member with no migration and that property is kept.
    #
    # READ THIS BEFORE ADDING ANOTHER ENUM COLUMN ANYWHERE IN THIS REPO:
    # `validate_strings=True` is NOT the default, and without it a
    # string-member `Enum` validates NOTHING. Measured on SQLAlchemy 2.0.51,
    # both dialects: 'Strict', 'RedactionMode.STRICT' and 'nonsense' all bind
    # straight through a bare `SAEnum(*values)` and land in the column. The
    # obvious spelling is the silently-permissive one. With the flag they raise
    # LookupError at bind and NULL still passes -- which is the pairing this
    # column needs: on the column whose job is proof, a value no code path can
    # produce must not be able to land, and "not recorded" must stay
    # expressible.
    #
    # And what is NOT claimed here, because it was nearly written as fact and
    # then measured: this column is NOT joining a guarantee `mode` and `status`
    # already enforce. Those columns have no such guarantee. `SAEnum(LLMCallMode)`
    # binds a bogus raw string unchallenged too --
    # **THE SAFETY THERE IS IN THE WRITERS, NOT IN THE TYPE**: every writer
    # assigns an enum MEMBER, so a bad string never reaches the bind. This
    # column is a plain `str` at the ORM layer with no member to assign, so the
    # writers cannot carry it and the type has to.
    redaction_mode: Mapped[str | None] = mapped_column(
        SAEnum(
            *get_args(RedactionMode),
            name="llm_redaction_mode",
            native_enum=False,
            length=16,
            validate_strings=True,
        )
    )
    redacted_counts: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSONB, "postgresql"))
    correlation_id: Mapped[str | None] = mapped_column(String(128))

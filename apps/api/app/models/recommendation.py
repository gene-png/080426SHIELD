"""Recommendation: output B of the design note rev 4, one row per item
(sections 5, 12.3 and 13; migration 0067). Admin only, never client-visible.

`scope` is `service` (one service's B) or `client` (the client-level
"Integrated recommendations"). A client-scope row has no service and no
deliverable; a service-scope row always has a service. Both are CHECK
constraints, not conventions.

Every enum column follows the `ai_runs` convention (`native_enum=False`, no
`values_callable`), so the STORED value is the member NAME (`SERVICE`,
`PENDING`), and the CHECK constraints below are written against that stored
spelling.

`expected_effect` is the structured effect list from P2/P3 (section 13);
`effect_status` is the consultant's verdict on the effect, separate from the
text's `status`. `priority_inputs` holds the section 12.3 inputs as computed;
the AI never sets `priority_rank`.

There is deliberately NO artifact column: B is never written to a file the
client could be given (section 6).

Nothing reads or writes this table yet (N4 is schema only).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import conv

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin

_JSON = JSON().with_variant(JSONB, "postgresql")

#: "NULL IS NOT RECORDED" MEANS SQL NULL, and a plain `JSON` column writes
#: Python None as the JSON text 'null' (`risk_register.py`, review of
#: 655184cc, F3). A writer meaning "not recorded" leaves the attribute UNSET
#: (JSON evaluates None, so an unset column is left out of the INSERT) or
#: writes `sqlalchemy.null()`; never None. Pinned by
#: `test_not_recorded_json_is_sql_null_only_when_unset_or_written_as_sa_null`.
#: Not `JSON(none_as_null=True)`: that makes SQLAlchemy name the column in
#: EVERY insert, set or not (the reason `RiskEntry.other_axes` avoids it).


class RecommendationScope(enum.StrEnum):
    SERVICE = "service"
    CLIENT = "client"


class RecommendationKind(enum.StrEnum):
    GENERAL = "general"
    OWNED_TOOL = "owned_tool"
    CROSS_SERVICE = "cross_service"


class RecommendationEffectStatus(enum.StrEnum):
    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class RecommendationStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


#: The scope CHECKs, against the stored member NAMES. Named here so the
#: migration and the model cannot spell them differently.
CK_SCOPE_CLIENT = "ck_recommendations_client_scope_has_no_service"
CK_SCOPE_SERVICE = "ck_recommendations_service_scope_has_service"
CK_ORIGIN = "ck_recommendations_origin_vocabulary"


class Recommendation(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(
            "scope <> 'CLIENT' OR (service_id IS NULL AND deliverable_id IS NULL)",
            name=conv(CK_SCOPE_CLIENT),
        ),
        CheckConstraint(
            "scope <> 'SERVICE' OR service_id IS NOT NULL",
            name=conv(CK_SCOPE_SERVICE),
        ),
        CheckConstraint(
            "origin IN ('ai', 'edited', 'consultant')",
            name=conv(CK_ORIGIN),
        ),
    )

    scope: Mapped[RecommendationScope] = mapped_column(
        SAEnum(RecommendationScope, name="recommendation_scope", native_enum=False, length=16),
        nullable=False,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), index=True
    )
    deliverable_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deliverables.id", ondelete="CASCADE")
    )
    integration_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("integration_runs.id", ondelete="SET NULL")
    )
    finding_id: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[RecommendationKind] = mapped_column(
        SAEnum(RecommendationKind, name="recommendation_kind", native_enum=False, length=16),
        nullable=False,
        default=RecommendationKind.GENERAL,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    # For `owned_tool` only.
    tool: Mapped[str | None] = mapped_column(String(255))
    axis: Mapped[str | None] = mapped_column(String(16))
    configuration: Mapped[str | None] = mapped_column(Text)
    # SQL NULL (see `_JSON`) is "not recorded"; [] is "no effect named".
    expected_effect: Mapped[list | None] = mapped_column(_JSON)
    effect_status: Mapped[RecommendationEffectStatus | None] = mapped_column(
        SAEnum(
            RecommendationEffectStatus,
            name="recommendation_effect_status",
            native_enum=False,
            length=16,
        )
    )
    # SQL NULL (see `_JSON`) is "not computed".
    priority_inputs: Mapped[dict | None] = mapped_column(_JSON)
    priority_rank: Mapped[int | None] = mapped_column(Integer)
    # `ai` | `edited` | `consultant` (advisor ruling, #736 6128447366, (d)):
    # `edited` is AI-drafted and then changed by a consultant, and P1's
    # context-sourcing rule keys on it. A plain string held by a CHECK, in the
    # lowercase spelling written here (not an SAEnum member name).
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="ai")
    status: Mapped[RecommendationStatus] = mapped_column(
        SAEnum(RecommendationStatus, name="recommendation_status", native_enum=False, length=16),
        nullable=False,
        default=RecommendationStatus.PENDING,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="SET NULL")
    )

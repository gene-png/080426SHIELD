"""Evidence link: one client file linked to one assessment row (EV-1, design
note rev 4, section 10.1; migration 0068).

A link says which row a file supports (`target_kind`, `target_code`, and for
CSF the `tier`) and what it shows (`supports`, from a fixed vocabulary per
kind). The AI suggests (`origin = "ai"`, `status = SUGGESTED`); a consultant
confirms or rejects, or adds a link directly (`origin = "consultant"`).

`assessment_id` HAS NO FOREIGN KEY: the three assessment tables (CSF, ZT,
ATT&CK) are three referents, so there is no single target. `target_kind`
discriminates, as `Service.kind` does for `Deliverable.parent_version`.

UNIQUENESS IS TWO PARTIAL INDEXES, NOT ONE CONSTRAINT. The design's key is
(`artifact_id`, `assessment_id`, `target_kind`, `target_code`, `tier`), but
`tier` is NULL for every ZT and ATT&CK link, and SQL treats NULLs as distinct,
so a plain UNIQUE would accept any number of duplicate ZT/ATT&CK links. One
index covers the untiered rows on the other four columns, one covers the
tiered rows on all five. Both carry `sqlite_where` and `postgresql_where`,
for `ai_runs`' reason: an index declared with only one of them is a plain
UNIQUE index on the other dialect.

A CHECK holds `tier` to CSF rows only: present exactly when `target_kind` is
`CSF_ROW`.

Enum columns follow the `ai_runs` convention (`native_enum=False`, no
`values_callable`): the STORED value is the member NAME (`CSF_ROW`,
`SUGGESTED`), and the CHECK is written against that spelling.

Nothing reads or writes this table yet (N5 is schema only). The existing
`evidence_artifact_id` columns stay, read-only, until a later migration.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import conv

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin

_JSON = JSON().with_variant(JSONB, "postgresql")


class EvidenceTargetKind(enum.StrEnum):
    CSF_ROW = "csf_row"
    ZT_CAPABILITY = "zt_capability"
    ATTACK_TECHNIQUE = "attack_technique"


class EvidenceLinkStatus(enum.StrEnum):
    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


_UNTIERED = "tier IS NULL"
_TIERED = "tier IS NOT NULL"


class EvidenceLink(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "evidence_links"
    __table_args__ = (
        CheckConstraint(
            "(target_kind = 'CSF_ROW' AND tier IS NOT NULL) "
            "OR (target_kind <> 'CSF_ROW' AND tier IS NULL)",
            name=conv("ck_evidence_links_tier_iff_csf_row"),
        ),
        Index(
            "uq_evidence_links_untiered",
            "artifact_id",
            "assessment_id",
            "target_kind",
            "target_code",
            unique=True,
            sqlite_where=text(_UNTIERED),
            postgresql_where=text(_UNTIERED),
        ),
        Index(
            "uq_evidence_links_tiered",
            "artifact_id",
            "assessment_id",
            "target_kind",
            "target_code",
            "tier",
            unique=True,
            sqlite_where=text(_TIERED),
            postgresql_where=text(_TIERED),
        ),
        Index("ix_evidence_links_assessment_id", "assessment_id"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # No ForeignKey: see the module docstring.
    assessment_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    target_kind: Mapped[EvidenceTargetKind] = mapped_column(
        SAEnum(EvidenceTargetKind, name="evidence_target_kind", native_enum=False, length=32),
        nullable=False,
    )
    # The subcategory, capability or technique code.
    target_code: Mapped[str] = mapped_column(String(32), nullable=False)
    # CSF only (high / moderate / low, as `csf_dimension_scores.tier`).
    tier: Mapped[str | None] = mapped_column(String(16))
    # What the file shows, from a fixed vocabulary per kind: CSF the five
    # dimensions; ZT `implemented`; ATT&CK `detect`, `prevent`, `respond`.
    # NULL is "not recorded"; [] is "nothing".
    supports: Mapped[list | None] = mapped_column(_JSON)
    status: Mapped[EvidenceLinkStatus] = mapped_column(
        SAEnum(EvidenceLinkStatus, name="evidence_link_status", native_enum=False, length=16),
        nullable=False,
        default=EvidenceLinkStatus.SUGGESTED,
    )
    # `ai` | `consultant`.
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    suggested_by_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="SET NULL")
    )
    quote: Mapped[str | None] = mapped_column(Text)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

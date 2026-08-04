"""Questionnaire question catalog (static seed).

Ported from the pre-AI questionnaire surface. The `questions` table is the
persisted home for the rich interview questions extracted from the Kentro
Step 1.1 / 1.2 / 1.3 .docx files by
`apps/api/scripts/extract_csf_questionnaires.py` and loaded by
`apps/api/scripts/load_csf_tier_questionnaires.py`.

It sits *alongside* the CSF assessment models (`CsfAssessment` / `CsfAnswer`):
those score the 106 NIST subcategories directly, while a `Question` row carries
the human-facing interview prompt, interviewer cues, and the CSF subcategories
each prompt maps back to (`framework_activities`). A question's `pillar` column
holds the questionnaire *section* name (e.g. "Governance, Leadership &
Oversight").

The per-engagement response table from the original surface
(`questionnaire_responses`) is intentionally NOT ported: this repo already
captures answers via `CsfAnswer` / `ZtAnswer`, and the original model depended
on a `systems` table that does not exist here.
"""

from __future__ import annotations

from sqlalchemy import JSON, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin

# JSON list that is portable across the SQLite test DB and Postgres
# production (native JSONB on Postgres, generic JSON elsewhere).
_JSON_LIST = JSON().with_variant(JSONB, "postgresql")


class Question(UUIDPKMixin, TimestampMixin, Base):
    """Static seed loaded from packages/csf-data (and, later, packages/zt-data).

    Idempotently upserted by the loader on the natural key
    (framework_key, external_id).
    """

    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint(
            "framework_key",
            "external_id",
            name="uq_questions_framework_external_id",
        ),
    )

    # e.g. "csf-tier-high" / "csf-tier-moderate" / "csf-tier-low".
    framework_key: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # e.g. "CSF-1-1" (section.order within the source questionnaire).
    external_id: Mapped[str] = mapped_column(String(40), nullable=False)
    # Questionnaire section name (doubles as the per-pillar grouping key).
    pillar: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    # Interviewer follow-up cues shown under the main prompt.
    cues: Mapped[list] = mapped_column(_JSON_LIST, default=list)
    phase: Mapped[str | None] = mapped_column(String(40))
    # CSF 2.0 subcategory ids the prompt maps back to (e.g. ["GV.OC-01"]),
    # so the gap engine can tie free-form answers to NIST controls.
    framework_activities: Mapped[list] = mapped_column(_JSON_LIST, default=list)

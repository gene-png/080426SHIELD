"""The ATT&CK what-if (#802, migration 0060).

A scenario removes tools from the client's last confirmed ATT&CK assessment
(its pinned base) and records what a scoped AI re-assessment made of the
techniques those tools appear on. It is a WHAT-IF: nothing here is read by the
real assessment, a deliverable or the client's view.

Only the affected techniques are stored (`AttackScenarioRow`); every other
technique is the base assessment's own row, read live and never copied.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin

_JSON = JSON().with_variant(JSONB, "postgresql")


class AttackScenarioState(enum.StrEnum):
    """`draft`: the change list is saved, nothing has run. `confirmed`: the
    admin confirmed the change list and a run was started (its outcome is the
    run's, read from `ai_run_id`, never copied). `discarded`: set aside."""

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    DISCARDED = "discarded"


class AttackScenario(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "attack_scenarios"

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # The pinned base: the assessment this what-if is compared with, and what
    # it was at creation. A newer confirmed assessment makes the scenario
    # stale; it is never re-based.
    base_assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attack_assessments.id", ondelete="RESTRICT"), nullable=False
    )
    base_version: Mapped[int] = mapped_column(Integer, nullable=False)
    base_catalog_version: Mapped[str | None] = mapped_column(String(16))
    base_status_rules: Mapped[int] = mapped_column(Integer, nullable=False)
    # The confirmed change list: {"removed": [name], "added": []}.
    change_list: Mapped[dict] = mapped_column(_JSON, nullable=False)
    # The techniques the removed tools appear on: the only ones re-assessed.
    affected_codes: Mapped[list] = mapped_column(_JSON, nullable=False)
    state: Mapped[AttackScenarioState] = mapped_column(
        SAEnum(AttackScenarioState, name="attack_scenario_state", native_enum=False, length=16),
        nullable=False,
        default=AttackScenarioState.DRAFT,
    )
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="RESTRICT")
    )
    # The counted contract drops, by reason ({} when none; NULL before a run).
    dropped: Mapped[dict | None] = mapped_column(_JSON)
    # Techniques no batch re-assessed: they take the removal alone.
    not_reassessed: Mapped[list | None] = mapped_column(_JSON)
    # The advisor's addition (05:05Z): affected techniques whose computed
    # status after the change is HIGHER than in the base. NULL before a run.
    scored_higher: Mapped[int | None] = mapped_column(Integer)
    # The advisor's (b2), 08:10Z: the OFFERED tools added to the client's list
    # after the base was approved, by name. NULL before a run AND when that
    # could not be checked (`scenario.tools_added_since`); never [] for
    # "unknown". The count every surface shows is its length.
    tools_added_since_base: Mapped[list | None] = mapped_column(_JSON)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class AttackScenarioRow(UUIDPKMixin, TimestampMixin, Base):
    """One affected technique's lists under the scenario."""

    __tablename__ = "attack_scenario_rows"
    __table_args__ = (
        UniqueConstraint(
            "scenario_id", "technique_code", name="uq_attack_scenario_rows_scenario_technique"
        ),
    )

    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attack_scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    technique_code: Mapped[str] = mapped_column(String(32), nullable=False)
    detection_tools: Mapped[list] = mapped_column(_JSON, nullable=False)
    prevention_tools: Mapped[list] = mapped_column(_JSON, nullable=False)
    response_tools: Mapped[list] = mapped_column(_JSON, nullable=False)
    # The accepted AI rows behind these lists, with their rationale.
    ai_rows: Mapped[list] = mapped_column(_JSON, nullable=False)

"""Risk Register schemas (Work Order E)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RiskGateStatus(BaseModel):
    """Whether the Risk Register can be generated for a client.

    Threshold: a MITRE ATT&CK coverage mapping AND at least one of (CSF, ZT).
    """

    unlocked: bool
    has_attack: bool
    has_csf: bool
    has_zt: bool
    # ABSENT — no assessment of this kind exists. Remedy: create one.
    missing: list[str]
    # EXISTS but is not APPROVED or RELEASED, so it cannot be synthesized into a
    # register that will be exported under the client's name (#237). Remedy:
    # approve it.
    #
    # A SEPARATE FIELD, deliberately, though both feed one sentence. "There is no
    # ATT&CK mapping" and "the ATT&CK mapping is a draft" are different facts
    # with different remedies, and putting the second into a field named
    # `missing` would make the API assert something untrue in order to serve a
    # message. #234 shipped exactly that (`not_recorded` borrowed to mean
    # "retired") and had to correct it; it is not repeated here one issue later.
    #
    # Defaulted, so an older client parses a newer response (the C0 pattern).
    not_finalized: list[str] = []


class RiskEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    axis: str | None
    source: str | None
    source_id: str | None
    linked_techniques: list[str] | None
    linked_controls: list[str] | None
    likelihood: str | None
    impact: str | None
    tier: str | None
    compensating_controls: str | None
    residual_risk: str | None
    recommended_action: str | None
    rationale: str | None
    origin: str
    trust: str | None


class RiskRegisterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    version: int
    generated_by: uuid.UUID | None
    finalized_at: datetime | None
    created_at: datetime
    xlsx_artifact_id: uuid.UUID | None = None
    pdf_artifact_id: uuid.UUID | None = None
    docx_artifact_id: uuid.UUID | None = None
    xlsx_filename: str | None = None
    pdf_filename: str | None = None
    docx_filename: str | None = None
    entries: list[RiskEntryResponse]
    # Dashboard rollups (code-computed).
    tier_counts: dict[str, int] = {}
    axis_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    # risk_synthesize runs as concurrent batches (one llm_calls row each).
    # Additive + defaulted so older clients and stored payloads parse unchanged
    # (C0). A partial run KEEPS what succeeded rather than discarding it, so the
    # consultant must be told the draft is incomplete and by how much. Both are
    # 0 on a register read back from storage — they describe a generate run, not
    # the register itself.
    batches_total: int = 0
    batches_failed: int = 0

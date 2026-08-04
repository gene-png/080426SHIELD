"""Admin schemas (Phase 2 stage 7: intake queue)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.service import ServiceKind, ServiceStatus
from app.models.service_request import ServiceType
from app.models.user import UserRole
from app.schemas.intake import ClientProfileResponse


class AdminServiceDetail(BaseModel):
    """Minimal service lookup so a workspace can resolve its owning tenant."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ServiceKind
    status: ServiceStatus
    title: str
    client_id: uuid.UUID


class AdminAiStatus(BaseModel):
    """AI pipeline readiness. Never includes the API key itself."""

    mode: str
    provider: str
    model: str
    ready: bool
    detail: str


class AdminUserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    title: str | None
    role: UserRole
    last_login_at: datetime | None
    created_at: datetime


class AdminServiceRequestRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_type: ServiceType
    requested_at: datetime
    requested_by: AdminUserSummary
    notes: str | None
    deadline: datetime | None
    csf_target_tier: int | None
    csf_profile: str | None
    zt_target_stage: int | None
    fulfilled_service_id: uuid.UUID | None
    declined_at: datetime | None
    declined_reason: str | None


class AdminArtifactRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    mime_type: str
    size_bytes: int
    uploaded_by: uuid.UUID
    uploaded_at: datetime


class AdminIntakeQueueResponse(BaseModel):
    client: ClientProfileResponse | None
    intake_completed_at: datetime | None
    service_requests: list[AdminServiceRequestRow]
    artifacts: list[AdminArtifactRow]
    total_users: int


class FulfillServiceRequestResponse(BaseModel):
    """Result of publishing a service request: the live engagement workspace."""

    service_id: uuid.UUID
    service_type: ServiceType
    title: str
    already_fulfilled: bool


class AdminClientSummary(BaseModel):
    """One row in the platform-wide client list (platform admin view)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legal_name: str
    dba_name: str | None
    industry: str | None
    size_band: str | None
    intake_completed_at: datetime | None
    created_at: datetime


class AdminClientListResponse(BaseModel):
    clients: list[AdminClientSummary]


class AdminClientCreateRequest(BaseModel):
    """Minimum payload to create a new tenant. Intake fills in the rest."""

    legal_name: str
    dba_name: str | None = None
    industry: str | None = None
    size_band: str | None = None


class AdminDomainRow(BaseModel):
    """One approved email domain for a client (Work Order B2)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    domain: str
    created_at: datetime


class AdminDomainListResponse(BaseModel):
    domains: list[AdminDomainRow]


class AdminDomainCreateRequest(BaseModel):
    domain: str


# --------------------------------------------------------------------------- #
# Audit viewer (Sprint 5 T7): read surface over the two append-only stores.
# Read-only by construction — no create/update schemas exist for these.
# --------------------------------------------------------------------------- #


class AdminAuditEntryRow(BaseModel):
    """One append-only audit_entries row (Master Spec §11)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    at: datetime
    actor_user_id: uuid.UUID | None
    action: str
    target_type: str
    target_id: uuid.UUID | None
    details: dict | None
    correlation_id: str | None


class AdminAuditEntriesResponse(BaseModel):
    """A page of audit entries, newest first, plus an opaque next-page cursor."""

    entries: list[AdminAuditEntryRow]
    next_cursor: str | None = None


class AdminLlmCallRow(BaseModel):
    """One llm_calls row, audit-safe fields only.

    The model carries no API key, and error_message was made key-safe in
    Sprint 4 (Gemini fix), so every field here is safe to surface to an admin.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID | None
    client_id: uuid.UUID | None
    purpose: str
    prompt_version: str
    provider: str
    model: str
    mode: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int | None
    status: str
    error_message: str | None
    redacted_counts: dict | None
    requested_by: uuid.UUID
    requested_at: datetime
    completed_at: datetime | None
    correlation_id: str | None


class AdminLlmCallsResponse(BaseModel):
    """A page of llm_calls, newest first, plus an opaque next-page cursor."""

    calls: list[AdminLlmCallRow]
    next_cursor: str | None = None

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


class AdminLlmKeyRequest(BaseModel):
    """An API key pasted by an admin (issue 2).

    `provider` defaults to the configured `SHIELD_LLM_PROVIDER` so the common
    case is a single field. The key itself is never echoed back.
    """

    api_key: str
    provider: str | None = None


class AdminAiStatus(BaseModel):
    """AI pipeline readiness. Never includes the API key itself."""

    mode: str
    provider: str
    model: str
    ready: bool
    detail: str
    # Issue 2: whether this deployment can accept a pasted key at runtime, and
    # where the current key came from ("database" | "environment" | "none").
    # The UI uses these to decide whether to offer "Load a key", and to reset
    # its "I acknowledged offline mode" flag when the key changes.
    can_configure: bool = False
    key_source: str = "none"


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
    # Issue 3: NULL means active. Present so the Management UI can label an
    # archived tenant instead of silently hiding it when include_archived=true.
    archived_at: datetime | None = None
    # Issue 7: counts that let the intake-queue org index show, per row, how
    # much work is waiting without a second request per organization.
    open_request_count: int = 0
    total_request_count: int = 0


class AdminClientListResponse(BaseModel):
    clients: list[AdminClientSummary]


class AdminUserRow(BaseModel):
    """One user inside a tenant, for the Management UI's user list (issue 3)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    title: str | None
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class AdminUserListResponse(BaseModel):
    users: list[AdminUserRow]


class AdminUserPatchRequest(BaseModel):
    """Deactivate / reactivate a user (issue 3).

    Deactivation is the removal primitive: routes/auth.py already refuses
    sign-in for ``is_active=False``, so flipping this locks the account out
    immediately while retaining every row the user authored. Reversible by
    design — there is no hard user delete.
    """

    is_active: bool


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
    # NULL renders as "not recorded", never as "strict" (#144).
    redaction_mode: str | None
    redacted_counts: dict | None
    requested_by: uuid.UUID
    requested_at: datetime
    completed_at: datetime | None
    correlation_id: str | None


class AdminLlmCallsResponse(BaseModel):
    """A page of llm_calls, newest first, plus an opaque next-page cursor."""

    calls: list[AdminLlmCallRow]
    next_cursor: str | None = None


class AdminDeliverableRow(BaseModel):
    """One deliverable version as an admin sees it.

    Unlike the client-facing `ClientDeliverableResponse`, this carries
    UNRELEASED rows — that is the reason the surface exists. `status` and
    `client_visible` are derived in the route from columns that already exist
    (`superseded_by` / `released_at` / `finalized_at`), so nothing new is
    persisted and there is no second lifecycle to keep in step with §12.
    """

    id: uuid.UUID
    service_id: uuid.UUID
    service_kind: ServiceKind
    service_title: str
    title: str
    version: int
    #: generated | released | superseded
    status: str
    #: True ONLY for a released, non-superseded row — what the client can see.
    client_visible: bool
    finalized_at: datetime | None
    released_at: datetime | None
    pdf_artifact_id: uuid.UUID | None
    xlsx_artifact_id: uuid.UUID | None
    docx_artifact_id: uuid.UUID | None


class AdminDeliverableListResponse(BaseModel):
    items: list[AdminDeliverableRow]

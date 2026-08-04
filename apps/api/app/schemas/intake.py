"""Intake request/response schemas.

Master Spec §15 Phase 2: a six-step wizard with auto-save on blur. Three
routes back the wizard:

  GET   /intake/me     - current intake state (pre-fill the wizard).
  PATCH /intake        - partial update (auto-save target).
  POST  /intake/submit - finalize submission; sets intake_completed_at,
                        creates ServiceRequest rows, audits.

The client supplies a sparse payload to PATCH (only changed fields); the
schema's defaults of None are how that's encoded over the wire.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.service_request import CsfProfile, ServiceType


class ClientProfilePatch(BaseModel):
    """Partial update for the singleton client row.

    Every field is optional so the wizard can call this after each blur
    without resending the whole form. Strings normalize to None when empty
    so the user can clear a field by tabbing through with nothing in it.
    """

    legal_name: str | None = Field(default=None, max_length=255)
    dba_name: str | None = Field(default=None, max_length=255)
    website: HttpUrl | None = None
    size_band: str | None = Field(default=None, max_length=64)
    industry: str | None = Field(default=None, max_length=128)

    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=128)
    state: str | None = Field(default=None, max_length=64)
    postal_code: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=64)

    prompting_context: str | None = Field(default=None, max_length=4000)
    service_interests: list[ServiceType] | None = None


class IntakePatchRequest(BaseModel):
    """Auto-save body: any subset of client fields plus optional profile bits."""

    client: ClientProfilePatch | None = None
    display_name: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    timezone: str | None = Field(default=None, max_length=64)


class ServiceRequestInput(BaseModel):
    service_type: ServiceType
    notes: str | None = Field(default=None, max_length=4000)
    deadline: datetime | None = None

    # Client-supplied assessment targets (validated against service_type in the
    # submit route). Target tier/stage is 2-4: Tier/Stage 1 is the floor, so a
    # client never "targets" it.
    csf_target_tier: int | None = Field(default=None, ge=2, le=4)
    csf_profile: CsfProfile | None = None
    zt_target_stage: int | None = Field(default=None, ge=2, le=4)


class IntakeSubmitRequest(BaseModel):
    """Final submit. Must include the requested services (at least one)."""

    client: ClientProfilePatch
    service_requests: list[ServiceRequestInput] = Field(min_length=1)
    display_name: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    timezone: str | None = Field(default=None, max_length=64)


class ClientProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legal_name: str
    dba_name: str | None
    website: str | None
    size_band: str | None
    industry: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None
    prompting_context: str | None
    service_interests: list[str] | None
    intake_completed_at: datetime | None


class ServiceRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_type: ServiceType
    requested_by: uuid.UUID
    requested_at: datetime
    notes: str | None
    deadline: datetime | None
    csf_target_tier: int | None
    csf_profile: str | None
    zt_target_stage: int | None
    fulfilled_service_id: uuid.UUID | None
    declined_at: datetime | None
    declined_reason: str | None


class IntakeStateResponse(BaseModel):
    client: ClientProfileResponse | None
    service_requests: list[ServiceRequestResponse]
    intake_completed_at: datetime | None


class EngagementCreateRequest(BaseModel):
    """Start a new standalone engagement (a self-assessment project).

    Unlike the one-time intake, this can be called repeatedly — a client may
    run multiple independent engagements, including more than one of the same
    service type.
    """

    service_type: ServiceType
    name: str | None = Field(default=None, max_length=255)
    csf_target_tier: int | None = Field(default=None, ge=2, le=4)
    csf_profile: CsfProfile | None = None
    zt_target_stage: int | None = Field(default=None, ge=2, le=4)


class EngagementResponse(BaseModel):
    """One engagement = one Service (workspace) the client owns."""

    service_id: uuid.UUID
    service_type: ServiceType
    title: str
    # Service lifecycle (in_progress / released / ...).
    status: str
    # Self-assessment lifecycle for CSF/ZT engagements (draft / submitted /
    # approved / released); None for non-questionnaire services.
    assessment_status: str | None
    created_at: datetime

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

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.models.service_request import CsfProfile, ServiceType
from app.schemas._numeric import IntNotBool

# A URL scheme, RFC 3986 section 3.1, followed by "://".
_HAS_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


class ClientProfilePatch(BaseModel):
    """Partial update for the singleton client row.

    Every field is optional so the wizard can call this after each blur
    without resending the whole form. Strings normalize to None when empty
    so the user can clear a field by tabbing through with nothing in it.
    """

    legal_name: str | None = Field(default=None, max_length=255)
    dba_name: str | None = Field(default=None, max_length=255)
    website: HttpUrl | None = None

    @field_validator("website", mode="before")
    @classmethod
    def _website_scheme(cls, value: Any) -> Any:
        """IN-1 (#1049), ruling A (#736 6115773247): a website typed without a
        scheme ("kentro.com") gets `https://` in front instead of a schema 422.
        Covers save and submit, which both validate through this model. A value
        that already names a scheme, and anything that is not a string, is left
        for `HttpUrl` to judge unchanged. So is a schemeless value holding "@"
        (review of #1092): prefixing "mailto:a@b.com" would store a URL whose
        host is b.com, so it is left for `HttpUrl` to refuse."""
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if stripped and "@" not in stripped and not _HAS_SCHEME.match(stripped):
            return f"https://{stripped}"
        return stripped

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

    # Primary-contact override (0039). Rides the existing client auto-save path
    # rather than adding an endpoint. All NULL = the contact is the submitter.
    primary_contact_name: str | None = Field(default=None, max_length=255)
    primary_contact_email: str | None = Field(default=None, max_length=320)
    primary_contact_title: str | None = Field(default=None, max_length=255)
    primary_contact_phone: str | None = Field(default=None, max_length=64)


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

    # Client-supplied assessment targets. RANGE IS DELIBERATELY NOT DECLARED
    # HERE (#406) -- `routes/intake.py::_validate_targets` owns both ends, and
    # `app/assessment_targets.py` carries the reason at length. The short
    # version: a `ge`/`le` bound is refused by FastAPI's own handler as
    # "Request validation failed." under a `schema_*` reason with no client
    # copy behind it, on the surface where a client FIRST picks a target.
    # It also cannot see `service_type`, and the ladders differ -- DoD ZTRA
    # ends at Stage 3 where CISA ends at 4 (#125).
    #
    # `IntNotBool` is unaffected: it refuses `true` in a BeforeValidator, not
    # as a side effect of a floor above zero. `_numeric.py` says so explicitly.
    csf_target_tier: IntNotBool | None = None
    csf_profile: CsfProfile | None = None
    zt_target_stage: IntNotBool | None = None


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
    # NULL until the wizard's own Step 2 supplies it (D-080, #254).
    legal_name: str | None
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
    # Primary-contact override (0039). Returned so the wizard can re-open the
    # step with the override still checked and populated. Omitting these was the
    # same round-trip bug as the hardcoded-null contact fields: stored, applied,
    # and invisible to the form that wrote them.
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    primary_contact_title: str | None = None
    primary_contact_phone: str | None = None


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


class IntakeContactResponse(BaseModel):
    """The primary contact as the wizard will submit it.

    Returned so "Review & submit" can show what is about to be sent: the step
    previously rendered Organization, Services and Systems only, and the client
    had no way to check the POC details before committing (UX finding 3).
    """

    model_config = ConfigDict(from_attributes=True)

    display_name: str | None
    email: str
    title: str | None
    phone: str | None
    timezone: str | None
    # True when these values came from the client's primary-contact override
    # rather than from the submitting user's own account, so Review & submit can
    # say whose details are about to be sent.
    is_override: bool = False


class IntakeStateResponse(BaseModel):
    client: ClientProfileResponse | None
    service_requests: list[ServiceRequestResponse]
    intake_completed_at: datetime | None
    contact: IntakeContactResponse | None = None


class EngagementCreateRequest(BaseModel):
    """Start a new standalone engagement (a self-assessment project).

    Unlike the one-time intake, this can be called repeatedly — a client may
    run multiple independent engagements, including more than one of the same
    service type.
    """

    service_type: ServiceType
    name: str | None = Field(default=None, max_length=255)
    # Unbound for the reason given on `ServiceRequestInput` above. This route
    # reaches the same guard by a different path -- it RECONSTRUCTS a
    # `ServiceRequestInput` and hands it to `_validate_targets` -- so a bound
    # left on one model and not the other refuses the same value in two
    # different shapes depending on which endpoint the client reached.
    csf_target_tier: IntNotBool | None = None
    csf_profile: CsfProfile | None = None
    zt_target_stage: IntNotBool | None = None


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
    # #588: every report released for this service is withheld from the client
    # (#556, `is_stale_attack_deliverable`), so "released" must not read as
    # readable. False when nothing is released. REQUIRED: a default would turn
    # missing wiring into a confident "readable".
    withheld: bool
    created_at: datetime

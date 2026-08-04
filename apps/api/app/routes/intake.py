"""Intake routes.

Master Spec §15 Phase 2:
  - Six-step wizard with auto-save on blur.
  - Pre-fill from authenticated session everywhere possible (email,
    display name).
  - Service selection drives downstream pages.
  - Admin notification fires on intake submit (Phase 2 stage 8 - wired
    once notification infrastructure lands; this stage just emits the
    audit row, which the queue surfaces by querying it).
  - All copy in plain English (UI concern; API returns structured data).

Multi-tenant (post-0013): a CLIENT-role user is bound to their own
`client_id` at registration. Intake reads/writes that specific Client
row. Admins (platform-wide) can run intake on a chosen client
by passing X-Client-Id (the current_client dependency enforces this).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.db.session import get_db
from app.dependencies import current_client, current_user
from app.models._common import utcnow
from app.models.client import Client
from app.models.csf_assessment import CsfAssessment
from app.models.service import Service, ServiceKind
from app.models.service_request import ServiceRequest, ServiceType
from app.models.user import User, UserRole
from app.models.zt_assessment import ZtAssessment
from app.notifications import notify_role
from app.provisioning import (
    SELF_ASSESSMENT_TYPES,
    provision_self_assessment_service,
)
from app.schemas.intake import (
    EngagementCreateRequest,
    EngagementResponse,
    IntakePatchRequest,
    IntakeStateResponse,
    IntakeSubmitRequest,
    ServiceRequestInput,
)

_ZT_SERVICE_TYPES = (ServiceType.ZERO_TRUST_CISA, ServiceType.ZERO_TRUST_DOD)


def _validate_targets(item: ServiceRequestInput) -> None:
    """Enforce client-supplied assessment targets per selected service.

    The wizard gates this in the UI, but we re-check server-side so the
    target is never silently dropped (the consultant relies on it).
    """
    if item.service_type == ServiceType.NIST_CSF:
        if item.csf_target_tier is None or item.csf_profile is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="NIST CSF requires a target tier and profile before submitting.",
            )
    elif item.service_type in _ZT_SERVICE_TYPES and item.zt_target_stage is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Zero Trust requires a target stage before submitting.",
        )


router = APIRouter(prefix="/intake", tags=["intake"])


def _apply_patch_to_client(client: Client, patch: IntakePatchRequest) -> None:
    if patch.client is None:
        return
    data = patch.client.model_dump(exclude_unset=True)
    if "website" in data and data["website"] is not None:
        data["website"] = str(data["website"])
    if "service_interests" in data and data["service_interests"] is not None:
        data["service_interests"] = [v.value for v in data["service_interests"]]
    for field, value in data.items():
        setattr(client, field, value)


def _apply_profile_fields(user: User, fields: dict[str, str | None]) -> None:
    """Apply only the profile fields present in `fields` AND non-None.

    Caller is responsible for filtering down to set-and-non-None values so
    we don't overwrite a stored timezone with None just because the caller
    didn't include it (which would violate the NOT NULL on users.timezone).
    """
    for field, value in fields.items():
        if value is None:
            continue
        setattr(user, field, value)


@router.get(
    "",
    response_model=IntakeStateResponse,
    summary="Current intake state (pre-fill the wizard)",
)
def read_intake(
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> IntakeStateResponse:
    requests = (
        db.execute(
            select(ServiceRequest).where(
                ServiceRequest.client_id == client.id,
                ServiceRequest.requested_by == user.id,
            )
        )
        .scalars()
        .all()
    )
    return IntakeStateResponse(
        client=client,
        service_requests=list(requests),
        intake_completed_at=client.intake_completed_at,
    )


@router.patch(
    "",
    response_model=IntakeStateResponse,
    summary="Auto-save intake (partial update)",
)
def patch_intake(
    body: IntakePatchRequest,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> IntakeStateResponse:
    if client.intake_completed_at is not None:
        # Allow edits but reset the completion stamp so the admin queue
        # can re-surface the row as updated. The spec doesn't forbid
        # re-edits and §6.4 ("never ask for the same data twice") implies
        # the client may circle back without losing data.
        client.intake_completed_at = None

    _apply_patch_to_client(client, body)
    _apply_profile_fields(
        user,
        body.model_dump(
            exclude_unset=True,
            include={"display_name", "title", "phone", "timezone"},
        ),
    )

    db.commit()
    db.refresh(client)
    db.refresh(user)

    requests = (
        db.execute(
            select(ServiceRequest).where(
                ServiceRequest.client_id == client.id,
                ServiceRequest.requested_by == user.id,
            )
        )
        .scalars()
        .all()
    )
    return IntakeStateResponse(
        client=client,
        service_requests=list(requests),
        intake_completed_at=client.intake_completed_at,
    )


@router.post(
    "/submit",
    response_model=IntakeStateResponse,
    status_code=status.HTTP_200_OK,
    summary="Finalize intake submission",
)
def submit_intake(
    body: IntakeSubmitRequest,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> IntakeStateResponse:
    if not body.client.legal_name or body.client.legal_name == "(pending intake)":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Organization legal name is required to submit intake.",
        )

    _apply_patch_to_client(
        client,
        IntakePatchRequest(client=body.client),
    )
    _apply_profile_fields(
        user,
        body.model_dump(
            exclude_unset=True,
            include={"display_name", "title", "phone", "timezone"},
        ),
    )

    seen: set[str] = set()
    created_requests: list[ServiceRequest] = []
    for item in body.service_requests:
        # Don't write two requests for the same service in one submit.
        key = item.service_type.value
        if key in seen:
            continue
        seen.add(key)
        _validate_targets(item)
        sr = ServiceRequest(
            service_type=item.service_type,
            client_id=client.id,
            requested_by=user.id,
            notes=item.notes,
            deadline=item.deadline,
            csf_target_tier=item.csf_target_tier,
            csf_profile=item.csf_profile.value if item.csf_profile else None,
            zt_target_stage=item.zt_target_stage,
        )
        db.add(sr)
        created_requests.append(sr)

    # Auto-provision an engagement workspace + seeded draft assessment for each
    # questionnaire-driven service (CSF / Zero Trust) so the client can start
    # their self-assessment straight from the "received" screen. Skip kinds
    # already provisioned (e.g. on a re-submit) to avoid duplicate workspaces.
    db.flush()  # assign ids to the freshly-created requests
    existing_kinds = set(
        db.execute(select(Service.kind).where(Service.client_id == client.id)).scalars().all()
    )
    for sr in created_requests:
        if sr.service_type not in SELF_ASSESSMENT_TYPES:
            continue
        kind = ServiceKind(sr.service_type.value)
        if kind in existing_kinds:
            continue
        provision_self_assessment_service(db, sr, org_name=client.legal_name, actor_user_id=user.id)
        existing_kinds.add(kind)

    client.intake_completed_at = utcnow()

    audit(
        db,
        action="client.intake_submitted",
        target_type="client",
        target_id=client.id,
        actor_user_id=user.id,
        details={
            "services": sorted(seen),
            "user_count": 1,
        },
    )

    # Master Spec §15 Phase 2: "Admin notification fires on intake submit."
    # Fan out to every admin so any consultant on the engagement sees it.
    # AI Prompt §6.12: the link must resolve to a working page.
    services_label = ", ".join(sorted(seen))
    notify_role(
        db,
        role=UserRole.ADMIN,
        event_type="intake.submitted",
        title="New intake submitted",
        body=(f"{client.legal_name} requested: {services_label}. " "Review in the admin queue."),
        link="/admin/queue",
    )

    db.commit()
    db.refresh(client)

    all_requests = (
        db.execute(
            select(ServiceRequest).where(
                ServiceRequest.client_id == client.id,
                ServiceRequest.requested_by == user.id,
            )
        )
        .scalars()
        .all()
    )
    return IntakeStateResponse(
        client=client,
        service_requests=list(all_requests),
        intake_completed_at=client.intake_completed_at,
    )


# ---------------------------------------------------------------------------
# Engagements (multiple independent self-assessment projects per client)
# ---------------------------------------------------------------------------

_ZT_KINDS = (ServiceKind.ZERO_TRUST_CISA, ServiceKind.ZERO_TRUST_DOD)


def _latest_assessment_status(db: Session, svc: Service) -> str | None:
    """Self-assessment lifecycle status for a CSF/ZT engagement, else None.

    Reports the latest NON-discarded assessment (D-031): a discarded draft is
    retired from the engagement card, and a discarded-only service reads as
    having no active assessment (None), never "discarded".
    """
    if svc.kind == ServiceKind.NIST_CSF:
        row = db.execute(
            select(CsfAssessment.status)
            .where(
                CsfAssessment.service_id == svc.id,
                CsfAssessment.status != "discarded",
            )
            .order_by(CsfAssessment.version.desc())
            .limit(1)
        ).scalar_one_or_none()
    elif svc.kind in _ZT_KINDS:
        row = db.execute(
            select(ZtAssessment.status)
            .where(
                ZtAssessment.service_id == svc.id,
                ZtAssessment.status != "discarded",
            )
            .order_by(ZtAssessment.version.desc())
            .limit(1)
        ).scalar_one_or_none()
    else:
        return None
    return getattr(row, "value", row) if row is not None else None


def _engagement_response(db: Session, svc: Service) -> EngagementResponse:
    return EngagementResponse(
        service_id=svc.id,
        service_type=ServiceType(svc.kind.value),
        title=svc.title,
        status=getattr(svc.status, "value", svc.status),
        assessment_status=_latest_assessment_status(db, svc),
        created_at=svc.created_at,
    )


@router.get(
    "/engagements",
    response_model=list[EngagementResponse],
    summary="List the client's engagements (one per Service/workspace)",
)
def list_engagements(
    _user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> list[EngagementResponse]:
    svcs = (
        db.execute(
            select(Service)
            .where(Service.client_id == client.id)
            .order_by(Service.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [_engagement_response(db, s) for s in svcs]


@router.post(
    "/engagements",
    response_model=EngagementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new self-assessment engagement (repeatable; allows multiples)",
)
def create_engagement(
    body: EngagementCreateRequest,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> EngagementResponse:
    if body.service_type not in SELF_ASSESSMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only NIST CSF and Zero Trust can be started as a self-service engagement.",
        )
    if not client.legal_name or client.legal_name == "(pending intake)":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Complete your organization profile in intake before starting an engagement.",
        )

    # Reuse the submit-time target validation (CSF needs tier+profile, ZT a stage).
    _validate_targets(
        ServiceRequestInput(
            service_type=body.service_type,
            csf_target_tier=body.csf_target_tier,
            csf_profile=body.csf_profile,
            zt_target_stage=body.zt_target_stage,
        )
    )

    sr = ServiceRequest(
        service_type=body.service_type,
        client_id=client.id,
        requested_by=user.id,
        csf_target_tier=body.csf_target_tier,
        csf_profile=body.csf_profile.value if body.csf_profile else None,
        zt_target_stage=body.zt_target_stage,
    )
    db.add(sr)
    db.flush()

    # Intentionally NOT guarded by "kind already exists" — multiple engagements
    # of the same type are allowed; each is its own project/workspace.
    svc = provision_self_assessment_service(
        db,
        sr,
        org_name=client.legal_name,
        actor_user_id=user.id,
        title=body.name,
    )

    audit(
        db,
        action="engagement.created",
        target_type="service",
        target_id=svc.id,
        actor_user_id=user.id,
        details={"service_type": body.service_type.value, "title": svc.title},
    )
    notify_role(
        db,
        role=UserRole.ADMIN,
        event_type="engagement.created",
        title="New engagement started",
        body=f"{client.legal_name} started: {svc.title}. Review in the admin queue.",
        link="/admin/queue",
    )

    db.commit()
    db.refresh(svc)
    return _engagement_response(db, svc)

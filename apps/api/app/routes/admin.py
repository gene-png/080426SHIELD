"""Admin routes.

Master Spec §15 Phase 2 acceptance:
  - "Submitting intake reflects correctly in the admin queue with the
    new-lead timestamp."
  - "All intake data round-trips correctly: client enters X, admin reads X."

Phase 2 ships the read-only intake queue plus client-tenant management
(create client, approve/remove email domains); later assessment workflow
surfaces build on this.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.db.session import get_db
from app.dependencies import require_role
from app.models.artifact import Artifact
from app.models.audit_entry import AuditEntry
from app.models.client import Client
from app.models.client_domain import ClientDomain
from app.models.llm_call import LLMCall, LLMCallStatus
from app.models.service import Service, ServiceKind, ServiceStatus
from app.models.service_request import ServiceRequest, ServiceType
from app.models.user import User, UserRole
from app.schemas.admin import (
    AdminAiStatus,
    AdminArtifactRow,
    AdminAuditEntriesResponse,
    AdminAuditEntryRow,
    AdminClientCreateRequest,
    AdminClientListResponse,
    AdminClientSummary,
    AdminDomainCreateRequest,
    AdminDomainListResponse,
    AdminDomainRow,
    AdminIntakeQueueResponse,
    AdminLlmCallRow,
    AdminLlmCallsResponse,
    AdminServiceDetail,
    AdminServiceRequestRow,
    AdminUserSummary,
    FulfillServiceRequestResponse,
)
from app.schemas.intake import ClientProfileResponse
from app.security.email_domains import domain_of, is_generic_provider, is_reserved_domain

router = APIRouter(prefix="/admin", tags=["admin"])

_admin_required = Depends(require_role(UserRole.ADMIN))

# Cursor pagination: keyset on (timestamp desc, id desc) so we never OFFSET a
# growing append-only store. The cursor is opaque base64 of "<iso>|<uuid>".
_MAX_PAGE = 200
_DEFAULT_PAGE = 50


def _encode_cursor(at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{at.isoformat()}|{row_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        at_str, id_str = raw.rsplit("|", 1)
        return datetime.fromisoformat(at_str), uuid.UUID(id_str)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason": "bad_cursor", "message": "Pagination cursor is invalid."},
        ) from exc


# Human-readable service titles used when a request graduates to a workspace.
_SERVICE_TITLES: dict[ServiceType, str] = {
    ServiceType.TECH_DEBT: "Technical Debt Review",
    ServiceType.ZERO_TRUST_CISA: "Zero Trust (CISA ZTMM 2.0)",
    ServiceType.ZERO_TRUST_DOD: "Zero Trust (DoD ZTRA)",
    ServiceType.NIST_CSF: "NIST CSF 2.0 Assessment",
    ServiceType.ATTACK_COVERAGE: "MITRE ATT&CK Coverage",
}


@router.get(
    "/intake-queue",
    response_model=AdminIntakeQueueResponse,
    summary="Intake queue (admin)",
)
def intake_queue(
    _admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
    client_id: uuid.UUID | None = None,
) -> AdminIntakeQueueResponse:
    """Cross-tenant intake queue.

    Without `client_id` filter: shows requests/artifacts from all clients
    (consultant overview). The `client` field in the response is then the
    most-recently-created tenant for display continuity; treat it as advisory.
    With `client_id`: scopes to that tenant.
    """
    if client_id is not None:
        client = db.get(Client, client_id)
        if client is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found.",
            )
    else:
        client = db.execute(
            select(Client).order_by(Client.created_at.desc()).limit(1)
        ).scalar_one_or_none()

    sr_stmt = select(ServiceRequest, User).join(User, ServiceRequest.requested_by == User.id)
    if client_id is not None:
        sr_stmt = sr_stmt.where(ServiceRequest.client_id == client_id)
    sr_stmt = sr_stmt.order_by(ServiceRequest.requested_at.desc())
    rows = db.execute(sr_stmt).all()
    service_requests: list[AdminServiceRequestRow] = []
    for sr, requester in rows:
        service_requests.append(
            AdminServiceRequestRow(
                id=sr.id,
                service_type=sr.service_type,
                requested_at=sr.requested_at,
                requested_by=AdminUserSummary.model_validate(requester, from_attributes=True),
                notes=sr.notes,
                deadline=sr.deadline,
                csf_target_tier=sr.csf_target_tier,
                csf_profile=sr.csf_profile,
                zt_target_stage=sr.zt_target_stage,
                fulfilled_service_id=sr.fulfilled_service_id,
                declined_at=sr.declined_at,
                declined_reason=sr.declined_reason,
            )
        )

    art_stmt = select(Artifact)
    if client_id is not None:
        art_stmt = art_stmt.where(Artifact.client_id == client_id)
    art_stmt = art_stmt.order_by(Artifact.uploaded_at.desc())
    artifact_rows = db.execute(art_stmt).scalars().all()
    artifacts = [AdminArtifactRow.model_validate(a, from_attributes=True) for a in artifact_rows]

    user_stmt = select(func.count()).select_from(User)
    if client_id is not None:
        user_stmt = user_stmt.where(User.client_id == client_id)
    total_users = db.execute(user_stmt).scalar_one()

    return AdminIntakeQueueResponse(
        client=(
            ClientProfileResponse.model_validate(client, from_attributes=True)
            if client is not None
            else None
        ),
        intake_completed_at=client.intake_completed_at if client else None,
        service_requests=service_requests,
        artifacts=artifacts,
        total_users=total_users,
    )


@router.get(
    "/clients",
    response_model=AdminClientListResponse,
    summary="List all clients (admin)",
)
def list_clients(
    _admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
) -> AdminClientListResponse:
    rows = db.execute(select(Client).order_by(Client.created_at.desc())).scalars().all()
    return AdminClientListResponse(
        clients=[AdminClientSummary.model_validate(r, from_attributes=True) for r in rows]
    )


@router.post(
    "/clients",
    response_model=AdminClientSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new client tenant (admin)",
)
def create_client(
    body: AdminClientCreateRequest,
    admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
) -> AdminClientSummary:
    legal_name = body.legal_name.strip()
    if not legal_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="legal_name is required.",
        )
    client = Client(
        legal_name=legal_name,
        dba_name=body.dba_name,
        industry=body.industry,
        size_band=body.size_band,
    )
    db.add(client)
    db.flush()
    audit(
        db,
        action="client.created",
        target_type="client",
        target_id=client.id,
        actor_user_id=admin.id,
        details={"legal_name": legal_name, "source": "admin"},
    )
    db.commit()
    db.refresh(client)
    return AdminClientSummary.model_validate(client, from_attributes=True)


@router.get(
    "/clients/{cid}",
    response_model=AdminClientSummary,
    summary="Client detail (admin)",
)
def get_client(
    cid: uuid.UUID,
    _admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
) -> AdminClientSummary:
    client = db.get(Client, cid)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found.",
        )
    return AdminClientSummary.model_validate(client, from_attributes=True)


@router.get(
    "/clients/{cid}/domains",
    response_model=AdminDomainListResponse,
    summary="List a client's approved email domains (admin)",
)
def list_client_domains(
    cid: uuid.UUID,
    _admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
) -> AdminDomainListResponse:
    if db.get(Client, cid) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found.")
    rows = (
        db.execute(
            select(ClientDomain).where(ClientDomain.client_id == cid).order_by(ClientDomain.domain)
        )
        .scalars()
        .all()
    )
    return AdminDomainListResponse(
        domains=[AdminDomainRow.model_validate(r, from_attributes=True) for r in rows]
    )


@router.post(
    "/clients/{cid}/domains",
    response_model=AdminDomainRow,
    status_code=status.HTTP_201_CREATED,
    summary="Approve an email domain for a client (admin)",
)
def add_client_domain(
    cid: uuid.UUID,
    body: AdminDomainCreateRequest,
    admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
) -> AdminDomainRow:
    if db.get(Client, cid) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found.")
    # Accept either a bare domain or a full email; normalize to the domain.
    raw = body.domain.strip().lower()
    domain = domain_of(raw) if "@" in raw else raw
    if not domain or "." not in domain:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter a valid domain, e.g. company.com.",
        )
    if is_generic_provider(domain):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Generic email providers can't be approved as a client domain.",
        )
    # Reserved/special-use TLDs (.test/.invalid/.localhost) pass the format
    # check but the email validator 422s them at registration, so a user could
    # never sign up on them (the beacon.test trap, D-019). Reject at approval
    # with a typed reason (D-016) the Management UI maps to friendly copy.
    if is_reserved_domain(domain):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "reason": "domain_reserved_tld",
                "message": (
                    "That's a reserved or special-use domain (like .test, "
                    ".invalid, or .localhost) that no one can register a real "
                    "email address on. Approve the organization's actual "
                    "domain instead."
                ),
            },
        )
    existing = db.execute(
        select(ClientDomain).where(ClientDomain.domain == domain)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That domain is already registered to a client.",
        )
    row = ClientDomain(client_id=cid, domain=domain, created_by=admin.id)
    db.add(row)
    db.flush()
    audit(
        db,
        action="client.domain.added",
        target_type="client",
        target_id=cid,
        actor_user_id=admin.id,
        details={"domain": domain},
    )
    db.commit()
    db.refresh(row)
    return AdminDomainRow.model_validate(row, from_attributes=True)


@router.delete(
    "/clients/{cid}/domains/{domain_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an approved email domain (admin)",
)
def remove_client_domain(
    cid: uuid.UUID,
    domain_id: uuid.UUID,
    admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    row = db.get(ClientDomain, domain_id)
    if row is None or row.client_id != cid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found.")
    db.delete(row)
    audit(
        db,
        action="client.domain.removed",
        target_type="client",
        target_id=cid,
        actor_user_id=admin.id,
        details={"domain": row.domain},
    )
    db.commit()


@router.delete(
    "/services/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive (remove) a service (admin)",
)
def archive_service(
    service_id: uuid.UUID,
    admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Soft-remove a service by archiving it. Data is retained per policy and
    the workspace drops out of active lists."""
    svc = db.get(Service, service_id)
    if svc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found.")
    svc.status = ServiceStatus.ARCHIVED
    audit(
        db,
        action="service.archived",
        target_type="service",
        target_id=svc.id,
        actor_user_id=admin.id,
        details={"client_id": str(svc.client_id), "kind": svc.kind.value},
    )
    db.commit()


@router.post(
    "/service-requests/{request_id}/fulfill",
    response_model=FulfillServiceRequestResponse,
    summary="Publish a service request for processing (admin)",
)
def fulfill_service_request(
    request_id: uuid.UUID,
    admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
) -> FulfillServiceRequestResponse:
    """Graduate a service request into a live engagement workspace.

    The admin reviews the client's inputs + uploads in the queue, then
    publishes: this opens the Service (status in_progress) so the consultant
    can run the assessment and the AI pipeline against vetted intake data.
    Idempotent — re-publishing returns the existing workspace.
    """
    sr = db.get(ServiceRequest, request_id)
    if sr is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service request not found.",
        )
    if sr.service_type == ServiceType.CONSULTATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Consultation requests are handled directly, not published as a service.",
        )
    if sr.fulfilled_service_id is not None:
        existing = db.get(Service, sr.fulfilled_service_id)
        if existing is not None:
            return FulfillServiceRequestResponse(
                service_id=existing.id,
                service_type=sr.service_type,
                title=existing.title,
                already_fulfilled=True,
            )

    client = db.get(Client, sr.client_id)
    org = client.legal_name if client is not None else "Client"
    svc = Service(
        kind=ServiceKind(sr.service_type.value),
        status=ServiceStatus.IN_PROGRESS,
        title=f"{org} — {_SERVICE_TITLES[sr.service_type]}",
        client_id=sr.client_id,
        source_request_id=sr.id,
        opened_by=admin.id,
    )
    db.add(svc)
    db.flush()
    sr.fulfilled_service_id = svc.id
    audit(
        db,
        action="service_request.fulfilled",
        target_type="service",
        target_id=svc.id,
        actor_user_id=admin.id,
        details={"service_type": sr.service_type.value, "request_id": str(sr.id)},
    )
    db.commit()
    db.refresh(svc)
    return FulfillServiceRequestResponse(
        service_id=svc.id,
        service_type=sr.service_type,
        title=svc.title,
        already_fulfilled=False,
    )


@router.get(
    "/services/{service_id}",
    response_model=AdminServiceDetail,
    summary="Service detail (admin) - resolves a workspace's owning tenant",
)
def get_service(
    service_id: uuid.UUID,
    _admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
) -> AdminServiceDetail:
    """Look up a service by id, including its client_id.

    Cross-tenant on purpose (admin-only, no X-Client-Id): the workspace UI
    calls this to discover which client a service belongs to, then sets that
    as the active tenant before its tenant-scoped data calls.
    """
    svc = db.get(Service, service_id)
    if svc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found.",
        )
    return AdminServiceDetail.model_validate(svc, from_attributes=True)


@router.get(
    "/ai-status",
    response_model=AdminAiStatus,
    summary="AI pipeline readiness (admin)",
)
def ai_status(_admin: Annotated[User, _admin_required]) -> AdminAiStatus:
    """Report whether AI features will actually run a live call.

    `ready` is true only when a real provider call will be made. Fixture mode
    (and live mode missing its key) report ready=false with a reason. The API
    key itself is never returned.
    """
    s = get_settings()
    mode = s.shield_llm_mode
    provider = s.shield_llm_provider
    model = s.shield_llm_model

    if mode != "live":
        return AdminAiStatus(
            mode=mode,
            provider=provider,
            model=model,
            ready=False,
            detail=(
                "Running in fixture mode — AI features are disabled. Set "
                "SHIELD_LLM_MODE=live and ANTHROPIC_API_KEY to enable."
            ),
        )
    # Reuse the single source of truth the boot preflight enforces (D-026):
    # key present, SDK importable (anthropic), and a real (non-placeholder)
    # model. The API key itself is never returned.
    ready, detail = s.live_llm_readiness()
    return AdminAiStatus(
        mode=mode,
        provider=provider,
        model=model,
        ready=ready,
        detail=detail,
    )


@router.get(
    "/audit-entries",
    response_model=AdminAuditEntriesResponse,
    summary="Read the append-only audit log (admin)",
)
def list_audit_entries(
    _admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
    action: Annotated[str | None, Query(description="Match actions by prefix.")] = None,
    target_type: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    correlation_id: str | None = None,
    at_from: datetime | None = None,
    at_to: datetime | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_PAGE)] = _DEFAULT_PAGE,
) -> AdminAuditEntriesResponse:
    """Cursor-paginated view of audit_entries, newest first.

    Read-only surface for the append-only store: no mutation route exists for
    audit rows (the DB trigger + before_flush guard forbid it). Keyset on
    (at desc, id desc) keeps the query index-friendly as the log grows.
    """
    stmt = select(AuditEntry)
    if action:
        stmt = stmt.where(AuditEntry.action.startswith(action))
    if target_type:
        stmt = stmt.where(AuditEntry.target_type == target_type)
    if actor_user_id is not None:
        stmt = stmt.where(AuditEntry.actor_user_id == actor_user_id)
    if correlation_id:
        stmt = stmt.where(AuditEntry.correlation_id == correlation_id)
    if at_from is not None:
        stmt = stmt.where(AuditEntry.at >= at_from)
    if at_to is not None:
        stmt = stmt.where(AuditEntry.at <= at_to)
    if cursor:
        c_at, c_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                AuditEntry.at < c_at,
                and_(AuditEntry.at == c_at, AuditEntry.id < c_id),
            )
        )
    stmt = stmt.order_by(AuditEntry.at.desc(), AuditEntry.id.desc()).limit(limit + 1)
    rows = db.execute(stmt).scalars().all()

    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = _encode_cursor(last.at, last.id)

    return AdminAuditEntriesResponse(
        entries=[AdminAuditEntryRow.model_validate(r, from_attributes=True) for r in rows],
        next_cursor=next_cursor,
    )


@router.get(
    "/llm-calls",
    response_model=AdminLlmCallsResponse,
    summary="Read the AI egress log (admin)",
)
def list_llm_calls(
    _admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
    client_id: uuid.UUID | None = None,
    purpose: str | None = None,
    provider: str | None = None,
    call_status: Annotated[LLMCallStatus | None, Query(alias="status")] = None,
    correlation_id: str | None = None,
    at_from: datetime | None = None,
    at_to: datetime | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_PAGE)] = _DEFAULT_PAGE,
) -> AdminLlmCallsResponse:
    """Cursor-paginated view of llm_calls, newest first.

    Read-only surface over the AI egress record. Only audit-safe fields are
    projected (see AdminLlmCallRow); the model holds no API key. Keyset on
    (requested_at desc, id desc).
    """
    stmt = select(LLMCall)
    if client_id is not None:
        stmt = stmt.where(LLMCall.client_id == client_id)
    if purpose:
        stmt = stmt.where(LLMCall.purpose == purpose)
    if provider:
        stmt = stmt.where(LLMCall.provider == provider)
    if call_status is not None:
        stmt = stmt.where(LLMCall.status == call_status)
    if correlation_id:
        stmt = stmt.where(LLMCall.correlation_id == correlation_id)
    if at_from is not None:
        stmt = stmt.where(LLMCall.requested_at >= at_from)
    if at_to is not None:
        stmt = stmt.where(LLMCall.requested_at <= at_to)
    if cursor:
        c_at, c_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                LLMCall.requested_at < c_at,
                and_(LLMCall.requested_at == c_at, LLMCall.id < c_id),
            )
        )
    stmt = stmt.order_by(LLMCall.requested_at.desc(), LLMCall.id.desc()).limit(limit + 1)
    rows = db.execute(stmt).scalars().all()

    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = _encode_cursor(last.requested_at, last.id)

    return AdminLlmCallsResponse(
        calls=[AdminLlmCallRow.model_validate(r, from_attributes=True) for r in rows],
        next_cursor=next_cursor,
    )

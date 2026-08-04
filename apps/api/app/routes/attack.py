"""MITRE ATT&CK Coverage service routes (Phase 5 stage 6).

Endpoint surface mirrors the CSF + ZT layouts but with coverage status
(covered/partial/gap/N/A) instead of a maturity scale, and a heatmap
analytics endpoint in place of scoring/gap.

  POST   /attack/services
  GET    /attack/catalog
  POST   /attack/services/{id}/assessments
  GET    /attack/services/{id}/assessments/latest
  PATCH  /attack/coverage/{coverage_id}
  POST   /attack/assessments/{id}/approve
  GET    /attack/services/{id}/heatmap
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.ai.diff import diff_keyed_rows
from app.ai.engine import run_job
from app.ai.llm import LLMClient
from app.ai.preview import AiPreviewPayload
from app.attack.analytics import compute as compute_heatmap
from app.attack.catalog import (
    TACTICS,
    TECHNIQUES,
)
from app.attack.catalog import (
    all_codes as attack_all_codes,
)
from app.attack.coverage import COVERAGE_DEFINITIONS, CoverageStatus
from app.attack.exporters import build_context as build_attack_context
from app.attack.exporters import render_docx as render_attack_docx
from app.attack.exporters import render_pdf as render_attack_pdf
from app.attack.exporters import render_xlsx as render_attack_xlsx
from app.audit import audit
from app.db.session import get_db
from app.deliverable_release import release_deliverable
from app.dependencies import current_client, current_user, require_role
from app.logging import get_logger
from app.models._common import utcnow
from app.models.artifact import Artifact, ArtifactOrigin
from app.models.attack_assessment import (
    AttackAssessment,
    AttackAssessmentStatus,
    AttackCoverage,
)
from app.models.capability import CapabilityItem, CapabilityList
from app.models.client import Client
from app.models.deliverable import Deliverable
from app.models.service import Service, ServiceKind, ServiceStatus
from app.models.user import User, UserRole
from app.routes.artifacts import _storage_dep
from app.schemas.attack import (
    AttackAssessmentResponse,
    AttackCoveragePatch,
    AttackCoverageResponse,
    AttackHeatmap,
    AttackRunAiResponse,
    AttackServiceCreateRequest,
    AttackServiceResponse,
    CatalogCoverageDefinition,
    CatalogResponse,
    CatalogTactic,
    CatalogTechnique,
    CoverageChange,
    TacticHeatmapEntry,
)
from app.schemas.tech_debt import DeliverableResponse
from app.security.rate_limit import enforce_ai_rate_limit
from app.storage import StorageBackend
from app.tech_debt.filename import SERVICE_SLUG_ATTACK, deliverable_filename
from app.tenant import (
    require_attack_assessment_in_tenant,
    require_service_in_tenant,
)

router = APIRouter(prefix="/attack", tags=["attack"])

_admin_required = Depends(require_role(UserRole.ADMIN))

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_coverage(rows: Iterable[AttackCoverage]) -> list[AttackCoverageResponse]:
    ordered = sorted(rows, key=lambda r: r.technique_code)
    out: list[AttackCoverageResponse] = []
    for r in ordered:
        status_enum = CoverageStatus(r.status) if r.status is not None else None
        out.append(
            AttackCoverageResponse(
                id=r.id,
                assessment_id=r.assessment_id,
                technique_code=r.technique_code,
                status=status_enum,
                notes=r.notes,
                evidence_artifact_id=r.evidence_artifact_id,
                locked=r.locked,
                detection_tools=r.detection_tools,
                prevention_tools=r.prevention_tools,
                response_tools=r.response_tools,
                rationale=r.rationale,
                answered_by=r.answered_by,
                answered_at=r.answered_at,
            )
        )
    return out


def _serialize_assessment(db: Session, a: AttackAssessment) -> AttackAssessmentResponse:
    rows = (
        db.execute(select(AttackCoverage).where(AttackCoverage.assessment_id == a.id))
        .scalars()
        .all()
    )
    return AttackAssessmentResponse(
        id=a.id,
        service_id=a.service_id,
        version=a.version,
        status=a.status,
        approved_at=a.approved_at,
        approved_by=a.approved_by,
        documents_stale=a.documents_stale,
        coverage=_serialize_coverage(rows),
    )


def _latest_assessment(db: Session, service_id: uuid.UUID) -> AttackAssessment | None:
    # D-031: a DISCARDED assessment is retired from every "latest" consumer.
    # The next-version mint uses _max_assessment_version, not this helper.
    return db.execute(
        select(AttackAssessment)
        .where(
            AttackAssessment.service_id == service_id,
            AttackAssessment.status != AttackAssessmentStatus.DISCARDED,
        )
        .order_by(AttackAssessment.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def _max_assessment_version(db: Session, service_id: uuid.UUID) -> int:
    """Highest version across ALL assessments, discarded included (D-031 version
    trap): the (service_id, version) unique constraint counts discarded rows."""
    return (
        db.execute(
            select(func.max(AttackAssessment.version)).where(
                AttackAssessment.service_id == service_id
            )
        ).scalar()
        or 0
    )


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


@router.post(
    "/services",
    response_model=AttackServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open an ATT&CK Coverage service (admin)",
)
def create_attack_service(
    body: AttackServiceCreateRequest,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> AttackServiceResponse:
    if body.kind != ServiceKind.ATTACK_COVERAGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service kind must be attack_coverage for this endpoint.",
        )
    svc = Service(
        kind=ServiceKind.ATTACK_COVERAGE,
        status=ServiceStatus.IN_PROGRESS,
        title=body.title,
        client_id=client.id,
        source_request_id=body.source_request_id,
        opened_by=user.id,
    )
    db.add(svc)
    db.flush()
    audit(
        db,
        action="attack.service.opened",
        target_type="service",
        target_id=svc.id,
        actor_user_id=user.id,
        details={"title": svc.title},
    )
    db.commit()
    db.refresh(svc)
    return AttackServiceResponse.model_validate(svc, from_attributes=True)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@router.get(
    "/catalog",
    response_model=CatalogResponse,
    summary="MITRE ATT&CK Enterprise reference catalog",
)
def get_catalog(
    _user: Annotated[User, Depends(current_user)],
) -> CatalogResponse:
    tactic_rows = [
        CatalogTactic(id=t.id, shortname=t.shortname, name=t.name, description=t.description)
        for t in TACTICS
    ]
    technique_rows = [
        CatalogTechnique(
            id=t.id,
            name=t.name,
            tactics=list(t.tactics),
            parent_id=t.parent_id,
            is_sub_technique=t.is_sub_technique,
        )
        for t in TECHNIQUES
    ]
    defs = [
        CatalogCoverageDefinition(
            status=d.status, short_label=d.short_label, description=d.description
        )
        for d in COVERAGE_DEFINITIONS
    ]
    parents = sum(1 for t in TECHNIQUES if not t.is_sub_technique)
    subs = len(TECHNIQUES) - parents
    return CatalogResponse(
        tactics=tactic_rows,
        techniques=technique_rows,
        coverage_definitions=defs,
        total_techniques=parents,
        total_sub_techniques=subs,
    )


# ---------------------------------------------------------------------------
# Assessments
# ---------------------------------------------------------------------------


@router.post(
    "/services/{service_id}/assessments",
    response_model=AttackAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new draft ATT&CK coverage assessment (admin)",
)
def create_assessment(
    service_id: uuid.UUID,
    response: Response,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> AttackAssessmentResponse:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.ATTACK_COVERAGE)
    prior = _latest_assessment(db, svc.id)
    # Draft-exists guard (SPRINT_3 T1, ported from CSF T7): this route used to
    # mint a new version on EVERY call and pre-seed ~600 coverage rows per mint,
    # so a client hammering "start assessment" produced unbounded v2, v3, v4…
    # drafts (the worst offender of the shared pattern). If an unsubmitted draft
    # is already open, return it idempotently (HTTP 200) instead of minting. A
    # new version is only cut once the prior draft has moved on (approved).
    if prior is not None and prior.status == AttackAssessmentStatus.DRAFT:
        _log.info(
            "attack_assessment_create_reused_open_draft",
            assessment_id=str(prior.id),
            version=prior.version,
            service_id=str(svc.id),
        )
        response.status_code = status.HTTP_200_OK
        return _serialize_assessment(db, prior)
    version = _max_assessment_version(db, svc.id) + 1
    assessment = AttackAssessment(
        service_id=svc.id,
        client_id=client.id,
        version=version,
        status=AttackAssessmentStatus.DRAFT,
    )
    db.add(assessment)
    db.flush()
    # Pre-seed an unscored coverage row per technique so the UI receives
    # a complete grid on the very first GET. 600+ rows but cheap.
    for t in TECHNIQUES:
        db.add(
            AttackCoverage(
                assessment_id=assessment.id,
                client_id=client.id,
                technique_code=t.id,
                status=None,
            )
        )
    audit(
        db,
        action="attack.assessment.created",
        target_type="attack_assessment",
        target_id=assessment.id,
        actor_user_id=user.id,
        details={"service_id": str(svc.id), "version": version},
    )
    db.commit()
    db.refresh(assessment)
    return _serialize_assessment(db, assessment)


@router.get(
    "/services/{service_id}/assessments/latest",
    response_model=AttackAssessmentResponse,
    summary="Most recent ATT&CK coverage assessment",
)
def latest_assessment(
    service_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> AttackAssessmentResponse:
    svc = require_service_in_tenant(db, service_id, client.id)
    a = _latest_assessment(db, svc.id)
    if a is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No assessment yet.",
        )
    if user.role != UserRole.ADMIN and a.status != AttackAssessmentStatus.RELEASED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ATT&CK assessments are admin-only until released.",
        )
    return _serialize_assessment(db, a)


# ---------------------------------------------------------------------------
# Coverage editing
# ---------------------------------------------------------------------------


@router.patch(
    "/coverage/{coverage_id}",
    response_model=AttackCoverageResponse,
    summary="Inline-update a single technique coverage row (admin)",
)
def patch_coverage(
    coverage_id: uuid.UUID,
    body: AttackCoveragePatch,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> AttackCoverageResponse:
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field is required.",
        )
    row = db.get(AttackCoverage, coverage_id)
    if row is None or row.client_id != client.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Coverage row not found.",
        )
    a = db.get(AttackAssessment, row.assessment_id)
    if a is None or a.status in (
        AttackAssessmentStatus.APPROVED,
        AttackAssessmentStatus.RELEASED,
        AttackAssessmentStatus.DISCARDED,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This assessment is locked.",
        )
    if "status" in data:
        new_status = data["status"]
        if new_status is None:
            row.status = None
        else:
            # Pydantic validated the enum value already.
            row.status = (
                new_status.value if isinstance(new_status, CoverageStatus) else str(new_status)
            )
    if "notes" in data:
        row.notes = data["notes"]
    if "evidence_artifact_id" in data:
        row.evidence_artifact_id = data["evidence_artifact_id"]
    if data.get("locked") is not None:
        row.locked = bool(data["locked"])
    for f in ("detection_tools", "prevention_tools", "response_tools", "rationale"):
        if f in data:
            setattr(row, f, data[f])
    row.answered_by = user.id
    row.answered_at = utcnow()
    audit(
        db,
        action="attack.coverage.updated",
        target_type="attack_coverage",
        target_id=row.id,
        actor_user_id=user.id,
        details={
            "technique_code": row.technique_code,
            "fields": sorted(data.keys()),
        },
    )
    db.commit()
    db.refresh(row)
    status_enum = CoverageStatus(row.status) if row.status is not None else None
    return AttackCoverageResponse(
        id=row.id,
        assessment_id=row.assessment_id,
        technique_code=row.technique_code,
        status=status_enum,
        notes=row.notes,
        evidence_artifact_id=row.evidence_artifact_id,
        locked=row.locked,
        detection_tools=row.detection_tools,
        prevention_tools=row.prevention_tools,
        response_tools=row.response_tools,
        rationale=row.rationale,
        answered_by=row.answered_by,
        answered_at=row.answered_at,
    )


def _llm_dep() -> LLMClient:
    return LLMClient.from_settings()


def _client_tool_names(db: Session, client_id: uuid.UUID) -> list[str]:
    """Tool names from the client's Tech Debt capability list(s), if any.

    ATT&CK maps the client's security tooling to techniques; the canonical
    source is the Tech Debt approved capability list (Work Order D2).
    """
    names = (
        db.execute(
            select(CapabilityItem.name)
            .join(CapabilityList, CapabilityItem.capability_list_id == CapabilityList.id)
            .join(Service, CapabilityList.service_id == Service.id)
            .where(
                Service.client_id == client_id,
                Service.kind == ServiceKind.TECH_DEBT,
            )
        )
        .scalars()
        .all()
    )
    return sorted({n.strip() for n in names if n and n.strip()})


_VALID_STATUSES = {s.value for s in CoverageStatus}
_DIFF_FIELDS = (
    "status",
    "detection_tools",
    "prevention_tools",
    "response_tools",
    "rationale",
)


@dataclass(frozen=True)
class AttackAiRequest:
    """Loaded state + outbound payload for the ATT&CK mitre_map run-ai job.

    Built once by :func:`build_attack_ai_request`; consumed by run-ai (which
    needs ``rows``/``locked_keys``/``valid_tools`` to validate and apply
    suggestions) and by the redaction-preview route (which only needs
    ``.preview``).
    """

    assessment: AttackAssessment
    rows: dict[str, AttackCoverage]
    locked_keys: frozenset[str]
    valid_tools: frozenset[str]
    preview: AiPreviewPayload


def build_attack_ai_request(db: Session, svc: Service, client: Client) -> AttackAiRequest:
    """Load the latest ATT&CK assessment and build the mitre_map run-ai payload.

    Raises the same typed 404/409s run-ai does. Reads only — never mutates.
    """
    a = _latest_assessment(db, svc.id)
    if a is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Create an assessment first."
        )
    if a.status in (AttackAssessmentStatus.APPROVED, AttackAssessmentStatus.RELEASED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This assessment is locked."
        )

    tools = _client_tool_names(db, client.id)
    rows = {
        r.technique_code: r
        for r in db.execute(select(AttackCoverage).where(AttackCoverage.assessment_id == a.id))
        .scalars()
        .all()
    }
    locked_keys = frozenset(code for code, r in rows.items() if r.locked)
    client_org = None if client.legal_name == "(pending intake)" else client.legal_name
    return AttackAiRequest(
        assessment=a,
        rows=rows,
        locked_keys=locked_keys,
        valid_tools=frozenset(t.lower() for t in tools),
        preview=AiPreviewPayload(
            job_name="mitre_map",
            inputs={"capability_list": tools, "technique_codes": sorted(rows)},
            client_org_name=client_org,
        ),
    )


@router.post(
    "/services/{service_id}/run-ai",
    response_model=AttackRunAiResponse,
    summary="Run the mitre_map AI job: suggest coverage + D/P/R per technique (admin)",
)
def run_ai(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
    llm: Annotated[LLMClient, Depends(_llm_dep)],
    _rl: Annotated[None, Depends(enforce_ai_rate_limit)],
) -> AttackRunAiResponse:
    """The ATT&CK 'Run AI'. Suggests coverage status + which listed tools provide
    Detection / Prevention / Response per technique, validating every cited tool
    against the client's capability list. AI suggests; locked rows are left
    untouched; code computes coverage % elsewhere. Returns a 'what changed' list.
    """
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.ATTACK_COVERAGE)
    req = build_attack_ai_request(db, svc, client)
    a, rows, locked_keys, valid_tools = (
        req.assessment,
        req.rows,
        req.locked_keys,
        req.valid_tools,
    )
    tools = req.preview.inputs["capability_list"]

    def _snap() -> dict[str, dict]:
        return {
            code: {
                "status": r.status,
                "detection_tools": list(r.detection_tools or []),
                "prevention_tools": list(r.prevention_tools or []),
                "response_tools": list(r.response_tools or []),
                "rationale": r.rationale,
            }
            for code, r in rows.items()
        }

    before = _snap()
    result = run_job(
        db,
        llm,
        req.preview.job_name,
        inputs=req.preview.inputs,
        requested_by=user.id,
        service_id=svc.id,
        client_id=client.id,
        client_org_name=req.preview.client_org_name,
        name_hints=req.preview.name_hints,
    )

    def _validate_tools(names: object) -> list[str]:
        if not isinstance(names, list):
            return []
        # Only tools that actually appear in the client's capability list.
        return [t for t in names if isinstance(t, str) and t.lower() in valid_tools]

    for sugg in (result.data or {}).get("techniques", []):
        if not isinstance(sugg, dict):
            continue
        row = rows.get(sugg.get("technique_code"))
        if row is None or row.locked:
            continue
        st = sugg.get("status")
        if isinstance(st, str) and st in _VALID_STATUSES:
            row.status = st
        if "detection_tools" in sugg:
            row.detection_tools = _validate_tools(sugg["detection_tools"])
        if "prevention_tools" in sugg:
            row.prevention_tools = _validate_tools(sugg["prevention_tools"])
        if "response_tools" in sugg:
            row.response_tools = _validate_tools(sugg["response_tools"])
        if isinstance(sugg.get("rationale"), str):
            row.rationale = sugg["rationale"]
        row.answered_by = user.id
        row.answered_at = utcnow()

    db.flush()
    after = _snap()
    diffs = diff_keyed_rows(before, after, _DIFF_FIELDS, locked_keys=locked_keys)
    changes = [
        CoverageChange(technique_code=d.key, field=ch.field, old=ch.old, new=ch.new)
        for d in diffs
        for ch in d.changes
    ]

    # D-031 concurrency: a discard racing this run must win. Re-read the parent
    # status before committing so suggestions never land in a discarded (or
    # newly locked) assessment.
    current_status = db.execute(
        select(AttackAssessment.status).where(AttackAssessment.id == a.id)
    ).scalar_one()
    if current_status in (
        AttackAssessmentStatus.DISCARDED,
        AttackAssessmentStatus.APPROVED,
        AttackAssessmentStatus.RELEASED,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "assessment_not_editable",
                "message": "This assessment was discarded or locked during the run.",
            },
        )

    a.documents_stale = True  # Work Order C3
    audit(
        db,
        action="attack.run_ai",
        target_type="attack_assessment",
        target_id=a.id,
        actor_user_id=user.id,
        details={"tools_available": len(tools), "changed_rows": len(diffs)},
    )
    db.commit()

    coverage = [
        AttackCoverageResponse.model_validate(r, from_attributes=True)
        for r in sorted(rows.values(), key=lambda r: r.technique_code)
    ]
    return AttackRunAiResponse(tools_available=len(tools), changed=changes, coverage=coverage)


@router.post(
    "/assessments/{assessment_id}/approve",
    response_model=AttackAssessmentResponse,
    summary="Approve the ATT&CK coverage assessment (admin)",
)
def approve_assessment(
    assessment_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> AttackAssessmentResponse:
    a = require_attack_assessment_in_tenant(db, assessment_id, client.id)
    if a.status == AttackAssessmentStatus.APPROVED:
        return _serialize_assessment(db, a)
    if a.status == AttackAssessmentStatus.RELEASED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment already released.",
        )
    a.status = AttackAssessmentStatus.APPROVED
    a.approved_at = utcnow()
    a.approved_by = user.id
    audit(
        db,
        action="attack.assessment.approved",
        target_type="attack_assessment",
        target_id=a.id,
        actor_user_id=user.id,
        details={"version": a.version},
    )
    db.commit()
    db.refresh(a)
    return _serialize_assessment(db, a)


@router.post(
    "/assessments/{assessment_id}/discard",
    response_model=AttackAssessmentResponse,
    summary="Discard a draft ATT&CK coverage assessment (admin, D-031)",
)
def discard_assessment(
    assessment_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> AttackAssessmentResponse:
    """Soft-delete an unapproved draft. DRAFT -> discarded (one audit row);
    re-discard is idempotent; approved/released -> typed 409. Conditional UPDATE
    ... WHERE status='draft' for the concurrency contract (D-031)."""
    a = require_attack_assessment_in_tenant(db, assessment_id, client.id)
    if a.status == AttackAssessmentStatus.DISCARDED:
        return _serialize_assessment(db, a)  # idempotent, no audit
    if a.status != AttackAssessmentStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "not_discardable",
                "message": "Only a draft assessment can be discarded.",
            },
        )
    coverage_count = db.execute(
        select(func.count()).select_from(AttackCoverage).where(AttackCoverage.assessment_id == a.id)
    ).scalar_one()
    scored_count = db.execute(
        select(func.count())
        .select_from(AttackCoverage)
        .where(AttackCoverage.assessment_id == a.id, AttackCoverage.status.is_not(None))
    ).scalar_one()
    result = db.execute(
        update(AttackAssessment)
        .where(
            AttackAssessment.id == a.id,
            AttackAssessment.status == AttackAssessmentStatus.DRAFT,
        )
        .values(status=AttackAssessmentStatus.DISCARDED)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.refresh(a)
        if a.status == AttackAssessmentStatus.DISCARDED:
            return _serialize_assessment(db, a)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "not_discardable",
                "message": "Only a draft assessment can be discarded.",
            },
        )
    audit(
        db,
        action="attack.assessment.discarded",
        target_type="attack_assessment",
        target_id=a.id,
        actor_user_id=user.id,
        details={
            "service_id": str(a.service_id),
            "version": a.version,
            "coverage_count": coverage_count,
            "scored_count": scored_count,
        },
    )
    _log.info(
        "attack_assessment_discarded",
        assessment_id=str(a.id),
        version=a.version,
        service_id=str(a.service_id),
        scored_count=scored_count,
    )
    db.commit()
    db.refresh(a)
    return _serialize_assessment(db, a)


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------


@router.get(
    "/services/{service_id}/heatmap",
    response_model=AttackHeatmap,
    summary="Coverage heatmap for the latest ATT&CK assessment (admin)",
)
def heatmap(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> AttackHeatmap:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.ATTACK_COVERAGE)
    a = _latest_assessment(db, svc.id)
    if a is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No assessment yet.",
        )
    valid = attack_all_codes()
    rows = (
        db.execute(select(AttackCoverage).where(AttackCoverage.assessment_id == a.id))
        .scalars()
        .all()
    )
    coverage_map: dict[str, str | None] = {
        r.technique_code: r.status for r in rows if r.technique_code in valid
    }
    rollup = compute_heatmap(coverage_map)
    return AttackHeatmap(
        assessment_id=a.id,
        version=a.version,
        total_techniques=rollup.total_techniques,
        total_sub_techniques=rollup.total_sub_techniques,
        scored_count=rollup.scored_count,
        unscored_count=rollup.unscored_count,
        covered=rollup.covered,
        partial=rollup.partial,
        gap=rollup.gap,
        not_applicable=rollup.not_applicable,
        coverage_pct=rollup.coverage_pct,
        by_tactic=[
            TacticHeatmapEntry(
                tactic_id=tc.tactic_id,
                tactic_name=tc.tactic_name,
                technique_count=tc.technique_count,
                sub_technique_count=tc.sub_technique_count,
                covered=tc.covered,
                partial=tc.partial,
                gap=tc.gap,
                not_applicable=tc.not_applicable,
                unscored=tc.unscored,
                coverage_pct=tc.coverage_pct,
            )
            for tc in rollup.by_tactic
        ],
    )


# ---------------------------------------------------------------------------
# Deliverables
# ---------------------------------------------------------------------------


def _serialize_deliverable(db: Session, deliv: Deliverable) -> DeliverableResponse:
    pdf_title = None
    xlsx_title = None
    docx_title = None
    if deliv.pdf_artifact_id:
        a = db.get(Artifact, deliv.pdf_artifact_id)
        pdf_title = a.title if a else None
    if deliv.xlsx_artifact_id:
        a = db.get(Artifact, deliv.xlsx_artifact_id)
        xlsx_title = a.title if a else None
    if deliv.docx_artifact_id:
        a = db.get(Artifact, deliv.docx_artifact_id)
        docx_title = a.title if a else None
    return DeliverableResponse(
        id=deliv.id,
        service_id=deliv.service_id,
        title=deliv.title,
        summary=deliv.summary,
        version=deliv.version,
        pdf_artifact_id=deliv.pdf_artifact_id,
        xlsx_artifact_id=deliv.xlsx_artifact_id,
        docx_artifact_id=deliv.docx_artifact_id,
        pdf_filename=pdf_title,
        xlsx_filename=xlsx_title,
        docx_filename=docx_title,
        finalized_at=deliv.finalized_at,
        finalized_by=deliv.finalized_by,
        superseded_by=deliv.superseded_by,
        released_at=deliv.released_at,
        released_by=deliv.released_by,
    )


def _write_artifact(
    db: Session,
    *,
    storage: StorageBackend,
    user: User,
    client_id: uuid.UUID,
    filename: str,
    mime_type: str,
    data: bytes,
) -> Artifact:
    from hashlib import sha256

    key = f"deliverable/{user.id}/{uuid.uuid4()}/{filename}"
    storage.put(key, data, content_type=mime_type)
    art = Artifact(
        client_id=client_id,
        title=filename,
        file_storage_key=key,
        mime_type=mime_type,
        size_bytes=len(data),
        sha256=sha256(data).hexdigest(),
        origin=ArtifactOrigin.CONSULTANT_APPROVED,
        stage="attack.deliverable",
        uploaded_by=user.id,
    )
    db.add(art)
    db.flush()
    return art


@router.post(
    "/services/{service_id}/deliverables/finalize",
    response_model=DeliverableResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Render PDF + XLSX deliverable from the latest approved ATT&CK assessment (admin)",
)
def finalize_attack_deliverable(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(_storage_dep)],
) -> DeliverableResponse:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.ATTACK_COVERAGE)
    assessment = _latest_assessment(db, svc.id)
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No assessment yet.",
        )
    if assessment.status not in (
        AttackAssessmentStatus.APPROVED,
        AttackAssessmentStatus.RELEASED,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment must be approved before finalizing the deliverable.",
        )
    valid = attack_all_codes()
    coverage = (
        db.execute(select(AttackCoverage).where(AttackCoverage.assessment_id == assessment.id))
        .scalars()
        .all()
    )
    coverage_map: dict[str, str | None] = {
        r.technique_code: r.status for r in coverage if r.technique_code in valid
    }
    rollup = compute_heatmap(coverage_map)

    client_name = client.legal_name
    if client_name == "(pending intake)":
        client_name = None

    today = utcnow().date()
    existing = db.execute(select(Deliverable).where(Deliverable.service_id == svc.id)).all()
    next_version = len(existing) + 1

    pdf_name = deliverable_filename(
        company=client_name,
        service_slug=SERVICE_SLUG_ATTACK,
        extension="pdf",
        day=today,
        version=next_version,
    )
    xlsx_name = deliverable_filename(
        company=client_name,
        service_slug=SERVICE_SLUG_ATTACK,
        extension="xlsx",
        day=today,
        version=next_version,
    )
    docx_name = deliverable_filename(
        company=client_name,
        service_slug=SERVICE_SLUG_ATTACK,
        extension="docx",
        day=today,
        version=next_version,
    )

    ctx = build_attack_context(
        client_legal_name=client_name,
        service_title=svc.title,
        assessment=assessment,
        coverage=coverage,
        rollup=rollup,
    )
    pdf_bytes = render_attack_pdf(ctx)
    xlsx_bytes = render_attack_xlsx(ctx)
    docx_bytes = render_attack_docx(ctx)

    pdf_artifact = _write_artifact(
        db,
        storage=storage,
        user=user,
        client_id=client.id,
        filename=pdf_name,
        mime_type="application/pdf",
        data=pdf_bytes,
    )
    xlsx_artifact = _write_artifact(
        db,
        storage=storage,
        user=user,
        client_id=client.id,
        filename=xlsx_name,
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=xlsx_bytes,
    )
    from app.docx_export import DOCX_MIME

    docx_artifact = _write_artifact(
        db,
        storage=storage,
        user=user,
        client_id=client.id,
        filename=docx_name,
        mime_type=DOCX_MIME,
        data=docx_bytes,
    )

    summary_line = (
        f"Coverage: {rollup.coverage_pct}%. "
        f"{rollup.covered} covered, {rollup.partial} partial, {rollup.gap} gaps, "
        f"{rollup.not_applicable} N/A across {rollup.scored_count} scored techniques."
    )

    deliv = Deliverable(
        service_id=svc.id,
        title=f"{svc.title} v{next_version}",
        summary=summary_line,
        version=next_version,
        pdf_artifact_id=pdf_artifact.id,
        xlsx_artifact_id=xlsx_artifact.id,
        docx_artifact_id=docx_artifact.id,
        finalized_at=utcnow(),
        finalized_by=user.id,
    )
    db.add(deliv)
    db.flush()

    audit(
        db,
        action="attack.deliverable.finalized",
        target_type="deliverable",
        target_id=deliv.id,
        actor_user_id=user.id,
        details={
            "service_id": str(svc.id),
            "assessment_id": str(assessment.id),
            "assessment_version": assessment.version,
            "version": next_version,
            "coverage_pct": rollup.coverage_pct,
            "gap_count": rollup.gap,
        },
    )
    assessment.documents_stale = False  # Work Order C3
    db.commit()
    db.refresh(deliv)
    return _serialize_deliverable(db, deliv)


@router.get(
    "/services/{service_id}/deliverables/latest",
    response_model=DeliverableResponse,
    summary="Most recent ATT&CK deliverable for a service (admin)",
)
def latest_attack_deliverable(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> DeliverableResponse:
    # Deliverables are admin-only (Work Order A1): clients never see or
    # download them in-app.
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.ATTACK_COVERAGE)
    deliv = db.execute(
        select(Deliverable)
        .where(Deliverable.service_id == svc.id)
        .order_by(Deliverable.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    if deliv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No deliverable yet. Finalize one first.",
        )
    return _serialize_deliverable(db, deliv)


@router.post(
    "/deliverables/{deliverable_id}/release",
    response_model=DeliverableResponse,
    summary="Release a finalized ATT&CK deliverable to the client (admin, D-025)",
)
def release_attack_deliverable(
    deliverable_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> DeliverableResponse:
    deliv = release_deliverable(
        db,
        deliverable_id=deliverable_id,
        tenant_client_id=client.id,
        user=user,
        kinds=(ServiceKind.ATTACK_COVERAGE,),
        action="attack.deliverable.released",
    )
    return _serialize_deliverable(db, deliv)

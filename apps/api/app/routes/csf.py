"""NIST CSF 2.0 service routes (Phase 4 stage 2).

Endpoint surface:
  POST   /csf/services
         Open a CSF assessment service. Admin-only.
  GET    /csf/catalog
         Static reference data. Any signed-in role.
  POST   /csf/services/{service_id}/assessments
         Create a draft assessment for the service. Admin-only.
  GET    /csf/services/{service_id}/assessments/latest
         Most recent assessment (admin sees draft; client sees released).
  PATCH  /csf/answers/{answer_id}
         Inline update of one subcategory answer. Admin-only.
  POST   /csf/assessments/{assessment_id}/approve
         Flip status -> approved. Admin-only.
  GET    /csf/services/{service_id}/score
         Roll-up score for the latest assessment. Admin-only.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.ai.diff import diff_keyed_rows
from app.ai.engine import run_job
from app.ai.llm import LLMClient
from app.ai.preview import AiPreviewPayload
from app.audit import audit
from app.csf import playbook_export as csf_playbook_export
from app.csf.catalog import (
    CATEGORIES,
    FUNCTIONS,
    SUBCATEGORIES,
    all_codes,
    is_core,
    is_core_primary,
    is_supporting_or_supplemental,
    min_profile_for_category,
    subcategory_by_code,
)
from app.csf.exporters import build_context as build_csf_context
from app.csf.exporters import render_docx as render_csf_docx
from app.csf.exporters import render_pdf as render_csf_pdf
from app.csf.exporters import render_xlsx as render_csf_xlsx
from app.csf.gap import analyze as analyze_gaps
from app.csf.maturity import TIER_DEFINITIONS
from app.csf.playbook import (
    DimensionScores,
    Tier,
    gap_priority,
    is_gap,
    score_tier,
    weighted_floor_rollup,
)
from app.csf.scoring import compute as compute_score
from app.db.session import get_db
from app.deliverable_release import release_deliverable
from app.dependencies import current_client, current_user, require_role
from app.logging import get_logger
from app.models._common import utcnow
from app.models.artifact import Artifact, ArtifactOrigin
from app.models.client import Client
from app.models.csf_assessment import (
    CsfAnswer,
    CsfAssessment,
    CsfAssessmentStatus,
)
from app.models.csf_profile import CsfDimensionScore, CsfGapAction
from app.models.deliverable import Deliverable
from app.models.questionnaire import Question
from app.models.service import Service, ServiceKind, ServiceStatus
from app.models.service_request import ServiceRequest
from app.models.user import User, UserRole
from app.routes.artifacts import _storage_dep
from app.schemas.csf import (
    GAP_CHARACTERIZATIONS,
    GAP_PRIORITY_OVERRIDES,
    CatalogCategory,
    CatalogFunction,
    CatalogResponse,
    CatalogSubcategory,
    CatalogTier,
    CsfAnswerPatch,
    CsfAnswerResponse,
    CsfAssessmentResponse,
    CsfDimensionChange,
    CsfDimensionScorePatch,
    CsfDimensionScoreResponse,
    CsfGapActionResponse,
    CsfGapActionsResponse,
    CsfGapActionUpsert,
    CsfPlaybookExportResponse,
    CsfProfileResponse,
    CsfQuestionnaireResponse,
    CsfRunAiResponse,
    CsfScoreSummary,
    CsfSelfAssessmentSubmit,
    CsfServiceCreateRequest,
    CsfServiceResponse,
    EnterpriseProfileResponse,
    EnterpriseSubcategory,
    ExportedArtifact,
    FunctionScore,
    GapAnalysisResponse,
    GapItem,
    InterviewQuestion,
    ProfileSeedRequest,
)
from app.schemas.tech_debt import DeliverableResponse
from app.security.rate_limit import enforce_ai_rate_limit
from app.storage import StorageBackend
from app.tech_debt.filename import (
    SERVICE_SLUG_CSF_PLAYBOOK,
    SERVICE_SLUG_NIST_CSF,
    deliverable_filename,
)
from app.tenant import (
    require_csf_assessment_in_tenant,
    require_service_in_tenant,
)

router = APIRouter(prefix="/csf", tags=["csf"])

_log = get_logger(__name__)

_admin_required = Depends(require_role(UserRole.ADMIN))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_answers(rows: Iterable[CsfAnswer]) -> list[CsfAnswerResponse]:
    # Stable ordering: by NIST code so the workspace tab renders predictably.
    ordered = sorted(rows, key=lambda r: r.subcategory_code)
    return [CsfAnswerResponse.model_validate(r, from_attributes=True) for r in ordered]


def _client_target_tier(db: Session, service_id: uuid.UUID) -> int | None:
    """The CSF target tier the client chose at intake, via the source request.

    Lets the admin workspace default its gap target to the client's goal
    instead of a hardcoded tier.
    """
    svc = db.get(Service, service_id)
    if svc is None or svc.source_request_id is None:
        return None
    sr = db.get(ServiceRequest, svc.source_request_id)
    return sr.csf_target_tier if sr is not None else None


def _client_profile(db: Session, service_id: uuid.UUID) -> str | None:
    """The CSF impact profile the client chose at intake (LOW/MOD/HIGH)."""
    svc = db.get(Service, service_id)
    if svc is None or svc.source_request_id is None:
        return None
    sr = db.get(ServiceRequest, svc.source_request_id)
    return sr.csf_profile if sr is not None else None


def _serialize_assessment(db: Session, a: CsfAssessment) -> CsfAssessmentResponse:
    rows = db.execute(select(CsfAnswer).where(CsfAnswer.assessment_id == a.id)).scalars().all()
    return CsfAssessmentResponse(
        id=a.id,
        service_id=a.service_id,
        version=a.version,
        status=a.status,
        approved_at=a.approved_at,
        approved_by=a.approved_by,
        documents_stale=a.documents_stale,
        answers=_serialize_answers(rows),
        client_target_tier=_client_target_tier(db, a.service_id),
        client_profile=_client_profile(db, a.service_id),
    )


def _latest_assessment(db: Session, service_id: uuid.UUID) -> CsfAssessment | None:
    # D-031: a DISCARDED assessment is retired from every "latest" consumer.
    # The next-version mint uses _max_assessment_version, not this helper.
    return db.execute(
        select(CsfAssessment)
        .where(
            CsfAssessment.service_id == service_id,
            CsfAssessment.status != CsfAssessmentStatus.DISCARDED,
        )
        .order_by(CsfAssessment.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def _max_assessment_version(db: Session, service_id: uuid.UUID) -> int:
    """Highest version across ALL assessments, discarded included (D-031 version
    trap): the (service_id, version) unique constraint counts discarded rows."""
    return (
        db.execute(
            select(func.max(CsfAssessment.version)).where(CsfAssessment.service_id == service_id)
        ).scalar()
        or 0
    )


# Impact profile (set at intake) -> the interview-questionnaire framework_key
# loaded into the `questions` table. HIGH is the most complete questionnaire,
# so it's the fallback when no profile has been chosen yet.
_PROFILE_TO_TIER_KEY = {
    "LOW": "csf-tier-low",
    "MOD": "csf-tier-moderate",
    "HIGH": "csf-tier-high",
}
_DEFAULT_TIER_KEY = "csf-tier-high"


@router.get(
    "/services/{service_id}/questionnaire",
    response_model=CsfQuestionnaireResponse,
    summary="Interview prompts for the service's impact tier",
)
def get_interview_questionnaire(
    service_id: uuid.UUID,
    _user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfQuestionnaireResponse:
    """Tier-resolved interview prompts (read-only).

    Each prompt carries the CSF subcategories it informs so the workspace can
    surface it inline on those subcategory cards. Any signed-in role scoped to
    the tenant may read it.
    """
    require_service_in_tenant(db, service_id, client.id)
    profile = _client_profile(db, service_id)
    framework_key = _PROFILE_TO_TIER_KEY.get((profile or "").upper(), _DEFAULT_TIER_KEY)
    rows = (
        db.execute(
            select(Question)
            .where(Question.framework_key == framework_key)
            .order_by(Question.order_index)
        )
        .scalars()
        .all()
    )
    return CsfQuestionnaireResponse(
        framework_key=framework_key,
        profile=profile,
        questions=[
            InterviewQuestion(
                external_id=q.external_id,
                section_name=q.pillar,
                order_index=q.order_index,
                stem=q.stem,
                cues=list(q.cues or []),
                csf_subcategories=list(q.framework_activities or []),
            )
            for q in rows
        ],
    )


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


@router.post(
    "/services",
    response_model=CsfServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open a CSF assessment service (admin)",
)
def create_csf_service(
    body: CsfServiceCreateRequest,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfServiceResponse:
    if body.kind != ServiceKind.NIST_CSF:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service kind must be nist_csf for this endpoint.",
        )
    svc = Service(
        kind=ServiceKind.NIST_CSF,
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
        action="csf.service.opened",
        target_type="service",
        target_id=svc.id,
        actor_user_id=user.id,
        details={"title": svc.title},
    )
    db.commit()
    db.refresh(svc)
    return CsfServiceResponse.model_validate(svc, from_attributes=True)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@router.get(
    "/catalog",
    response_model=CatalogResponse,
    summary="NIST CSF 2.0 reference catalog",
)
def get_catalog(
    _user: Annotated[User, Depends(current_user)],
) -> CatalogResponse:
    functions: list[CatalogFunction] = []
    for fn in FUNCTIONS:
        categories: list[CatalogCategory] = []
        for cat in CATEGORIES:
            if cat.function != fn.code:
                continue
            subs = [
                CatalogSubcategory(
                    code=s.code,
                    function=s.function.value,
                    category=s.category,
                    name=s.name,
                    outcome=s.outcome,
                    min_profile=min_profile_for_category(s.category),
                )
                for s in SUBCATEGORIES
                if s.category == cat.code
            ]
            categories.append(
                CatalogCategory(
                    code=cat.code,
                    function=cat.function.value,
                    name=cat.name,
                    purpose=cat.purpose,
                    subcategories=subs,
                )
            )
        functions.append(
            CatalogFunction(
                code=fn.code.value,
                name=fn.name,
                purpose=fn.purpose,
                categories=categories,
            )
        )
    tiers = [
        CatalogTier(tier=int(t.tier), short_label=t.short_label, description=t.description)
        for t in TIER_DEFINITIONS
    ]
    return CatalogResponse(
        functions=functions,
        tiers=tiers,
        total_subcategories=len(SUBCATEGORIES),
    )


# ---------------------------------------------------------------------------
# Assessments
# ---------------------------------------------------------------------------


@router.post(
    "/services/{service_id}/assessments",
    response_model=CsfAssessmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new draft assessment for the service (admin)",
)
def create_assessment(
    service_id: uuid.UUID,
    response: Response,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfAssessmentResponse:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
    prior = _latest_assessment(db, svc.id)
    # Draft-exists guard (SPRINT_2 T7): this route used to mint a new version on
    # EVERY call, so a client hammering "start assessment" produced unbounded
    # v2, v3, v4… drafts. If an unsubmitted draft is already open, return it
    # idempotently (HTTP 200) instead of minting. A new version is only cut once
    # the prior draft has moved on (submitted/approved/released). This mirrors
    # the approve route's idempotent-200 shape rather than a 409, so callers
    # that expect a usable assessment back keep working unchanged.
    if prior is not None and prior.status == CsfAssessmentStatus.DRAFT:
        _log.info(
            "csf_assessment_create_reused_open_draft",
            assessment_id=str(prior.id),
            version=prior.version,
            service_id=str(svc.id),
        )
        response.status_code = status.HTTP_200_OK
        return _serialize_assessment(db, prior)
    version = _max_assessment_version(db, svc.id) + 1
    assessment = CsfAssessment(
        service_id=svc.id,
        client_id=client.id,
        version=version,
        status=CsfAssessmentStatus.DRAFT,
    )
    db.add(assessment)
    db.flush()
    # Pre-create empty answer rows so the workspace UI gets a deterministic
    # answer grid back from the very first GET. Cheap (~106 rows).
    for sc in SUBCATEGORIES:
        db.add(
            CsfAnswer(
                assessment_id=assessment.id,
                client_id=client.id,
                subcategory_code=sc.code,
            )
        )
    audit(
        db,
        action="csf.assessment.created",
        target_type="csf_assessment",
        target_id=assessment.id,
        actor_user_id=user.id,
        details={"service_id": str(svc.id), "version": version},
    )
    db.commit()
    db.refresh(assessment)
    _log.info(
        "csf_assessment_created",
        assessment_id=str(assessment.id),
        version=version,
        service_id=str(svc.id),
    )
    return _serialize_assessment(db, assessment)


@router.get(
    "/services/{service_id}/assessments/latest",
    response_model=CsfAssessmentResponse,
    summary="Most recent assessment for the service",
)
def latest_assessment(
    service_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfAssessmentResponse:
    svc = require_service_in_tenant(db, service_id, client.id)
    assessment = _latest_assessment(db, svc.id)
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No assessment yet.",
        )
    # Phase 4 keeps assessment scoreboards admin-only until the
    # deliverable is released to the client (mirrors Phase 3 stage 9).
    if user.role != UserRole.ADMIN and assessment.status != CsfAssessmentStatus.RELEASED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSF assessments are admin-only until released.",
        )
    return _serialize_assessment(db, assessment)


# ---------------------------------------------------------------------------
# Answer editing
# ---------------------------------------------------------------------------


@router.patch(
    "/answers/{answer_id}",
    response_model=CsfAnswerResponse,
    summary="Inline-update a single subcategory answer (admin)",
)
def patch_answer(
    answer_id: uuid.UUID,
    body: CsfAnswerPatch,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfAnswerResponse:
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field is required.",
        )
    row = db.get(CsfAnswer, answer_id)
    if row is None or row.client_id != client.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Answer not found.",
        )
    # Refuse edits to approved, released, or discarded assessments (D-031: a
    # stale tab must not write into an assessment the admin already discarded).
    a = db.get(CsfAssessment, row.assessment_id)
    if a is None or a.status in (
        CsfAssessmentStatus.APPROVED,
        CsfAssessmentStatus.RELEASED,
        CsfAssessmentStatus.DISCARDED,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This assessment is locked.",
        )
    # Validation: subcategory code already pinned at create-time, so we
    # only validate the tier values that arrive here.
    if "maturity_tier" in data and data["maturity_tier"] is not None:
        t = int(data["maturity_tier"])
        if not 1 <= t <= 4:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="maturity_tier must be 1-4.",
            )
        row.maturity_tier = t
    elif "maturity_tier" in data:
        row.maturity_tier = None
    if "notes" in data:
        row.notes = data["notes"]
    if "evidence_artifact_id" in data:
        row.evidence_artifact_id = data["evidence_artifact_id"]
    if data.get("locked") is not None:
        row.locked = bool(data["locked"])
    row.answered_by = user.id
    row.answered_at = utcnow()
    audit(
        db,
        action="csf.answer.updated",
        target_type="csf_answer",
        target_id=row.id,
        actor_user_id=user.id,
        details={
            "subcategory_code": row.subcategory_code,
            "fields": sorted(data.keys()),
        },
    )
    db.commit()
    db.refresh(row)
    return CsfAnswerResponse.model_validate(row, from_attributes=True)


# ---------------------------------------------------------------------------
# Client self-assessment (client fills their own draft, then submits for review)
# ---------------------------------------------------------------------------


@router.get(
    "/services/{service_id}/self-assessment",
    response_model=CsfAssessmentResponse,
    summary="The client's own assessment for this service (any status)",
)
def get_self_assessment(
    service_id: uuid.UUID,
    _user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfAssessmentResponse:
    """Read the client's own assessment so they can fill the questionnaire.

    Tenant-scoped (current_client), so a client only ever reaches their own.
    Unlike the admin `assessments/latest`, this is not gated on RELEASED - the
    client owns these answers. The score/gap/deliverable stay admin-only until
    the report is released.
    """
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
    assessment = _latest_assessment(db, svc.id)
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No assessment yet.",
        )
    return _serialize_assessment(db, assessment)


@router.patch(
    "/self-assessment/answers/{answer_id}",
    response_model=CsfAnswerResponse,
    summary="Client updates one answer on their own draft self-assessment",
)
def patch_self_assessment_answer(
    answer_id: uuid.UUID,
    body: CsfAnswerPatch,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfAnswerResponse:
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field is required.",
        )
    row = db.get(CsfAnswer, answer_id)
    if row is None or row.client_id != client.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Answer not found.",
        )
    a = db.get(CsfAssessment, row.assessment_id)
    if a is None or a.status != CsfAssessmentStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Your self-assessment is no longer editable.",
        )
    if "maturity_tier" in data and data["maturity_tier"] is not None:
        t = int(data["maturity_tier"])
        if not 1 <= t <= 4:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="maturity_tier must be 1-4.",
            )
        row.maturity_tier = t
    elif "maturity_tier" in data:
        row.maturity_tier = None
    if "notes" in data:
        row.notes = data["notes"]
    row.answered_by = user.id
    row.answered_at = utcnow()
    db.commit()
    db.refresh(row)
    return CsfAnswerResponse.model_validate(row, from_attributes=True)


@router.post(
    "/services/{service_id}/self-assessment/submit",
    response_model=CsfAssessmentResponse,
    summary="Client submits their self-assessment for admin review",
)
def submit_self_assessment(
    service_id: uuid.UUID,
    body: CsfSelfAssessmentSubmit,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfAssessmentResponse:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
    a = _latest_assessment(db, svc.id)
    if a is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No assessment yet.",
        )
    if a.status != CsfAssessmentStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This self-assessment has already been submitted.",
        )
    # Persist the (possibly adjusted) maturity target so the gap engine measures
    # against the client's goal.
    if body.target_tier is not None and svc.source_request_id is not None:
        sr = db.get(ServiceRequest, svc.source_request_id)
        if sr is not None:
            sr.csf_target_tier = body.target_tier
    a.status = CsfAssessmentStatus.SUBMITTED
    audit(
        db,
        action="csf.self_assessment.submitted",
        target_type="csf_assessment",
        target_id=a.id,
        actor_user_id=user.id,
        details={"service_id": str(svc.id), "version": a.version},
    )
    db.commit()
    db.refresh(a)
    return _serialize_assessment(db, a)


@router.post(
    "/assessments/{assessment_id}/approve",
    response_model=CsfAssessmentResponse,
    summary="Approve the assessment (admin)",
)
def approve_assessment(
    assessment_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfAssessmentResponse:
    a = require_csf_assessment_in_tenant(db, assessment_id, client.id)
    if a.status == CsfAssessmentStatus.APPROVED:
        return _serialize_assessment(db, a)
    if a.status == CsfAssessmentStatus.RELEASED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment already released.",
        )
    a.status = CsfAssessmentStatus.APPROVED
    a.approved_at = utcnow()
    a.approved_by = user.id
    audit(
        db,
        action="csf.assessment.approved",
        target_type="csf_assessment",
        target_id=a.id,
        actor_user_id=user.id,
        details={"version": a.version},
    )
    db.commit()
    db.refresh(a)
    return _serialize_assessment(db, a)


@router.post(
    "/assessments/{assessment_id}/discard",
    response_model=CsfAssessmentResponse,
    summary="Discard a draft assessment (admin, D-031)",
)
def discard_assessment(
    assessment_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfAssessmentResponse:
    """Soft-delete an unapproved draft. DRAFT -> discarded (one audit row);
    re-discard is idempotent; SUBMITTED/APPROVED/RELEASED -> typed 409. A
    client-touched draft is still discardable (the UI warns with the answered
    count). Conditional UPDATE ... WHERE status='draft' for the concurrency
    contract (D-031)."""
    a = require_csf_assessment_in_tenant(db, assessment_id, client.id)
    if a.status == CsfAssessmentStatus.DISCARDED:
        return _serialize_assessment(db, a)  # idempotent, no audit
    if a.status != CsfAssessmentStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "not_discardable",
                "message": "Only a draft assessment can be discarded.",
            },
        )
    answer_count = db.execute(
        select(func.count()).select_from(CsfAnswer).where(CsfAnswer.assessment_id == a.id)
    ).scalar_one()
    answered_count = db.execute(
        select(func.count())
        .select_from(CsfAnswer)
        .where(
            CsfAnswer.assessment_id == a.id,
            or_(
                CsfAnswer.maturity_tier.is_not(None),
                CsfAnswer.notes.is_not(None),
                CsfAnswer.evidence_artifact_id.is_not(None),
            ),
        )
    ).scalar_one()
    result = db.execute(
        update(CsfAssessment)
        .where(CsfAssessment.id == a.id, CsfAssessment.status == CsfAssessmentStatus.DRAFT)
        .values(status=CsfAssessmentStatus.DISCARDED)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.refresh(a)
        if a.status == CsfAssessmentStatus.DISCARDED:
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
        action="csf.assessment.discarded",
        target_type="csf_assessment",
        target_id=a.id,
        actor_user_id=user.id,
        details={
            "service_id": str(a.service_id),
            "version": a.version,
            "answer_count": answer_count,
            "answered_count": answered_count,
        },
    )
    _log.info(
        "csf_assessment_discarded",
        assessment_id=str(a.id),
        version=a.version,
        service_id=str(a.service_id),
        answered_count=answered_count,
    )
    db.commit()
    db.refresh(a)
    return _serialize_assessment(db, a)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


@router.get(
    "/services/{service_id}/score",
    response_model=CsfScoreSummary,
    summary="Roll-up score for the latest assessment (admin)",
)
def score_latest(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfScoreSummary:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
    a = _latest_assessment(db, svc.id)
    if a is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No assessment yet.",
        )
    rows = db.execute(select(CsfAnswer).where(CsfAnswer.assessment_id == a.id)).scalars().all()
    answers: dict[str, int | None] = {r.subcategory_code: r.maturity_tier for r in rows}
    # Defensive: ignore unknown codes.
    valid = all_codes()
    answers = {k: v for k, v in answers.items() if k in valid}
    score = compute_score(answers)
    return CsfScoreSummary(
        assessment_id=a.id,
        version=a.version,
        total_subcategories=score.total_subcategories,
        answered_subcategories=score.answered_subcategories,
        coverage_pct=score.coverage_pct,
        average_tier=score.average_tier,
        overall_maturity_label=score.overall_maturity_label,
        by_function=[
            FunctionScore(
                function=fs.function.value,
                function_name=fs.function_name,
                subcategory_count=fs.subcategory_count,
                answered_count=fs.answered_count,
                average_tier=fs.average_tier,
                coverage_pct=fs.coverage_pct,
                weakest_subcategory_codes=list(fs.weakest_subcategory_codes),
            )
            for fs in score.by_function
        ],
    )


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------


@router.get(
    "/services/{service_id}/gap-analysis",
    response_model=GapAnalysisResponse,
    summary="Prioritized remediation gaps for the latest assessment (admin)",
)
def gap_analysis(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
    target_tier: int = 3,
    top_n: int = 20,
) -> GapAnalysisResponse:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
    a = _latest_assessment(db, svc.id)
    if a is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No assessment yet.",
        )
    rows = db.execute(select(CsfAnswer).where(CsfAnswer.assessment_id == a.id)).scalars().all()
    valid = all_codes()
    answers: dict[str, int | None] = {
        r.subcategory_code: r.maturity_tier for r in rows if r.subcategory_code in valid
    }
    notes: dict[str, str | None] = {
        r.subcategory_code: r.notes for r in rows if r.subcategory_code in valid
    }
    analysis = analyze_gaps(answers, notes=notes, target_tier=target_tier, top_n=top_n)
    return GapAnalysisResponse(
        assessment_id=a.id,
        version=a.version,
        target_tier=analysis.target_tier,
        target_label=analysis.target_label,
        total_gap_count=analysis.total_gap_count,
        unscored_count=len(analysis.unscored_codes),
        gap_count_by_function=analysis.gap_count_by_function,
        gaps=[
            GapItem(
                code=g.code,
                function=g.function.value,
                function_name=g.function_name,
                category=g.category,
                name=g.name,
                outcome=g.outcome,
                current_tier=g.current_tier,
                target_tier=g.target_tier,
                gap_size=g.gap_size,
                priority_score=g.priority_score,
                notes=g.notes,
            )
            for g in analysis.gaps
        ],
    )


# ---------------------------------------------------------------------------
# Full-Playbook tiered Working Profile (Work Order D4)
# ---------------------------------------------------------------------------

_VALID_TIERS = {t.value for t in Tier}


def _dims(row: CsfDimensionScore) -> DimensionScores:
    return DimensionScores(
        governance=row.governance,
        policy=row.policy,
        implementation=row.implementation,
        monitoring=row.monitoring,
        improvement=row.improvement,
    )


def _score_response(row: CsfDimensionScore) -> CsfDimensionScoreResponse:
    result = score_tier(_dims(row), has_evidence=row.has_evidence)
    return CsfDimensionScoreResponse(
        id=row.id,
        tier=row.tier,
        subcategory_code=row.subcategory_code,
        governance=row.governance,
        policy=row.policy,
        implementation=row.implementation,
        monitoring=row.monitoring,
        improvement=row.improvement,
        in_scope=row.in_scope,
        rationale=row.rationale,
        what_we_found=row.what_we_found,
        has_evidence=row.has_evidence,
        target_level=row.target_level,
        locked=row.locked,
        total=result.total,
        level=result.level,
        evidence_capped=result.evidence_capped,
    )


@router.post(
    "/services/{service_id}/profiles/seed",
    response_model=list[str],
    summary="Seed the tiered Working Profile rows for the requested tiers (admin)",
)
def seed_profiles(
    service_id: uuid.UUID,
    body: ProfileSeedRequest,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> list[str]:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
    a = _latest_assessment(db, svc.id)
    if a is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Create an assessment first."
        )
    tiers = [t for t in body.tiers if t in _VALID_TIERS]
    if not tiers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid tiers (high/moderate/low).",
        )
    existing = {
        (r.tier, r.subcategory_code)
        for r in db.execute(
            select(CsfDimensionScore.tier, CsfDimensionScore.subcategory_code).where(
                CsfDimensionScore.assessment_id == a.id
            )
        ).all()
    }
    created = 0
    for tier in tiers:
        for sc in SUBCATEGORIES:
            if (tier, sc.code) in existing:
                continue
            db.add(
                CsfDimensionScore(
                    assessment_id=a.id,
                    client_id=client.id,
                    tier=tier,
                    subcategory_code=sc.code,
                )
            )
            created += 1
    audit(
        db,
        action="csf.profiles_seeded",
        target_type="csf_assessment",
        target_id=a.id,
        actor_user_id=user.id,
        details={"tiers": tiers, "created": created},
    )
    db.commit()
    return tiers


@router.get(
    "/services/{service_id}/profile/{tier}",
    response_model=CsfProfileResponse,
    summary="The tiered Working Profile for one tier, with computed totals/levels (admin)",
)
def get_profile(
    service_id: uuid.UUID,
    tier: str,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfProfileResponse:
    if tier not in _VALID_TIERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown tier.")
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
    a = _latest_assessment(db, svc.id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No assessment yet.")
    rows = (
        db.execute(
            select(CsfDimensionScore)
            .where(
                CsfDimensionScore.assessment_id == a.id,
                CsfDimensionScore.tier == tier,
            )
            .order_by(CsfDimensionScore.subcategory_code)
        )
        .scalars()
        .all()
    )
    return CsfProfileResponse(tier=tier, rows=[_score_response(r) for r in rows])


@router.patch(
    "/dimension-scores/{score_id}",
    response_model=CsfDimensionScoreResponse,
    summary="Set dimension scores / scope / target / lock on one row (admin)",
)
def patch_dimension_score(
    score_id: uuid.UUID,
    body: CsfDimensionScorePatch,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfDimensionScoreResponse:
    row = db.get(CsfDimensionScore, score_id)
    if row is None or row.client_id != client.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Score row not found.")
    data = body.model_dump(exclude_unset=True)
    for f in (
        "governance",
        "policy",
        "implementation",
        "monitoring",
        "improvement",
        "in_scope",
        "rationale",
        "what_we_found",
        "has_evidence",
        "target_level",
        "locked",
    ):
        if f in data and data[f] is not None:
            setattr(row, f, data[f])
        elif f in data and f in ("rationale", "what_we_found", "target_level"):
            setattr(row, f, None)  # explicit clear allowed for nullable text/target
    db.commit()
    return _score_response(row)


@router.get(
    "/services/{service_id}/enterprise-profile",
    response_model=EnterpriseProfileResponse,
    summary="Roll the tiered profiles up to one Enterprise level per subcategory (admin)",
)
def enterprise_profile(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> EnterpriseProfileResponse:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
    a = _latest_assessment(db, svc.id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No assessment yet.")
    out, tiers_in_use = _enterprise_subcategories(db, a)
    return EnterpriseProfileResponse(tiers_in_use=sorted(tiers_in_use), subcategories=out)


def _enterprise_subcategories(
    db: Session, a: CsfAssessment
) -> tuple[list[EnterpriseSubcategory], set[str]]:
    """The weighted-floor Enterprise roll-up per in-scope subcategory."""
    rows = (
        db.execute(select(CsfDimensionScore).where(CsfDimensionScore.assessment_id == a.id))
        .scalars()
        .all()
    )
    by_subcat: dict[str, dict[str, CsfDimensionScore]] = {}
    tiers_in_use: set[str] = set()
    for r in rows:
        if not r.in_scope:
            continue
        by_subcat.setdefault(r.subcategory_code, {})[r.tier] = r
        tiers_in_use.add(r.tier)

    out: list[EnterpriseSubcategory] = []
    for code in sorted(by_subcat):
        tier_rows = by_subcat[code]
        tier_levels = {
            tier: score_tier(_dims(row), has_evidence=row.has_evidence).level
            for tier, row in tier_rows.items()
        }
        rollup = weighted_floor_rollup(
            {Tier(t): lvl for t, lvl in tier_levels.items()},
            # Real IG Core/Supporting classification from the catalog (T5).
            # Absent subcategories return safe defaults, keeping older
            # assessments on rules 1/3/4/6 unchanged (C0 additive pattern).
            is_core_primary=is_core_primary(code),
            is_supporting_or_supplemental=is_supporting_or_supplemental(code),
        )
        targets = [row.target_level for row in tier_rows.values() if row.target_level]
        target = max(targets) if targets else None
        gap = is_gap(rollup.score, target) if target is not None else False
        priority = (
            gap_priority(
                is_core=is_core(code),
                high_tier=Tier.HIGH.value in tier_rows,
                multi_system=len(tier_rows) > 1,
            )
            if gap
            else None
        )
        sc = subcategory_by_code(code)
        out.append(
            EnterpriseSubcategory(
                subcategory_code=code,
                name=getattr(sc, "name", code),
                function=str(getattr(sc, "function", "")),
                tier_levels=tier_levels,
                enterprise_level=rollup.score,
                rollup_rule=rollup.rule,
                target_level=target,
                gap=gap,
                priority=priority,
            )
        )
    return out, tiers_in_use


# ---------------------------------------------------------------------------
# POA&M / gap action plan (Sprint 5 T5, spec step 10)
# ---------------------------------------------------------------------------

_GAP_ACTION_FIELDS = (
    "characterization",
    "priority_override",
    "owner",
    "deadline",
    "resources",
    "success_criteria",
    "poam_ref",
)


def _gap_action_response(
    ent: EnterpriseSubcategory, action: CsfGapAction | None
) -> CsfGapActionResponse:
    """Merge one enterprise gap with its stored POA&M annotation. The default
    priority is the code-computed roll-up priority (`gap_priority()`); a stored
    `priority_override` wins for the effective value — the engine is untouched."""
    override = action.priority_override if action else None
    return CsfGapActionResponse(
        subcategory_code=ent.subcategory_code,
        name=ent.name,
        function=ent.function,
        enterprise_level=ent.enterprise_level,
        target_level=ent.target_level,
        default_priority=ent.priority,
        characterization=action.characterization if action else None,
        priority_override=override,
        owner=action.owner if action else None,
        deadline=action.deadline if action else None,
        resources=action.resources if action else None,
        success_criteria=action.success_criteria if action else None,
        poam_ref=action.poam_ref if action else None,
        effective_priority=override or ent.priority,
    )


def _load_gap_actions(db: Session, assessment_id: uuid.UUID) -> dict[str, CsfGapAction]:
    rows = (
        db.execute(select(CsfGapAction).where(CsfGapAction.assessment_id == assessment_id))
        .scalars()
        .all()
    )
    return {r.subcategory_code: r for r in rows}


@router.get(
    "/services/{service_id}/gap-actions",
    response_model=CsfGapActionsResponse,
    summary="Enterprise gaps with their POA&M action-plan annotations (admin)",
)
def list_gap_actions(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfGapActionsResponse:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
    a = _latest_assessment(db, svc.id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No assessment yet.")
    ent_rows, _ = _enterprise_subcategories(db, a)
    actions = _load_gap_actions(db, a.id)
    gaps = [r for r in ent_rows if r.gap]
    _log.info(
        "csf.gap_actions.list assessment=%s gaps=%d annotated=%d",
        a.id,
        len(gaps),
        len(actions),
    )
    return CsfGapActionsResponse(
        assessment_id=a.id,
        actions=[_gap_action_response(r, actions.get(r.subcategory_code)) for r in gaps],
    )


@router.put(
    "/services/{service_id}/gap-actions/{subcategory_code}",
    response_model=CsfGapActionResponse,
    summary="Upsert one gap's POA&M annotation (admin, autosave)",
)
def upsert_gap_action(
    service_id: uuid.UUID,
    subcategory_code: str,
    body: CsfGapActionUpsert,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CsfGapActionResponse:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
    a = _latest_assessment(db, svc.id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No assessment yet.")
    if subcategory_code not in all_codes():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "reason": "unknown_subcategory",
                "message": f"'{subcategory_code}' is not a NIST CSF 2.0 subcategory.",
            },
        )

    data = body.model_dump(exclude_unset=True)
    # D-016 typed validation for the two enumerated fields (empty string clears).
    ch = data.get("characterization")
    if ch and ch not in GAP_CHARACTERIZATIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "reason": "invalid_characterization",
                "message": "Characterization must be accept, mitigate, transfer, or avoid.",
            },
        )
    po = data.get("priority_override")
    if po and po not in GAP_PRIORITY_OVERRIDES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "reason": "invalid_priority",
                "message": "Priority override must be P1, P2, or P3.",
            },
        )

    row = db.execute(
        select(CsfGapAction).where(
            CsfGapAction.assessment_id == a.id,
            CsfGapAction.subcategory_code == subcategory_code,
        )
    ).scalar_one_or_none()
    created = row is None
    if row is None:
        row = CsfGapAction(
            assessment_id=a.id,
            client_id=client.id,
            subcategory_code=subcategory_code,
        )
        db.add(row)
    for f in _GAP_ACTION_FIELDS:
        if f in data:
            # Empty string means "clear" for the nullable annotation fields.
            setattr(row, f, data[f] or None)
    audit(
        db,
        action="csf.gap_action.upserted",
        target_type="csf_gap_action",
        target_id=a.id,
        actor_user_id=user.id,
        details={"subcategory_code": subcategory_code, "created": created},
    )
    db.commit()
    db.refresh(row)
    _log.info(
        "csf.gap_action.upserted assessment=%s subcat=%s created=%s",
        a.id,
        subcategory_code,
        created,
    )

    # Recompute the enterprise row so the response carries the up-to-date
    # default/effective priority (the engine is only read, never mutated).
    ent_rows, _ = _enterprise_subcategories(db, a)
    ent = next((r for r in ent_rows if r.subcategory_code == subcategory_code), None)
    if ent is None:
        # Annotated a subcategory that is not currently a gap (e.g. out of scope
        # or no target). Still return the stored values; no roll-up default.
        ent = EnterpriseSubcategory(
            subcategory_code=subcategory_code,
            name=getattr(subcategory_by_code(subcategory_code), "name", subcategory_code),
            function=str(getattr(subcategory_by_code(subcategory_code), "function", "")),
            tier_levels={},
            enterprise_level=0,
            rollup_rule=0,
            target_level=None,
            gap=False,
            priority=None,
        )
    return _gap_action_response(ent, row)


def _llm_dep() -> LLMClient:
    return LLMClient.from_settings()


_DIM_FIELDS = ("governance", "policy", "implementation", "monitoring", "improvement")
_RUN_FIELDS = (*_DIM_FIELDS, "what_we_found")


@dataclass(frozen=True)
class CsfAiRequest:
    """Loaded state + outbound payload for the CSF csf_score run-ai job.

    Built once by :func:`build_csf_ai_request`; consumed by both run-ai (which
    needs ``rows``/``locked_keys`` to apply and diff the suggestions) and the
    redaction-preview route (which only needs ``.preview``). Single source of the
    egress payload so preview can never diverge from what actually egresses.
    """

    assessment: CsfAssessment
    rows: dict[str, CsfDimensionScore]
    locked_keys: frozenset[str]
    preview: AiPreviewPayload


def build_csf_ai_request(db: Session, svc: Service, client: Client) -> CsfAiRequest:
    """Load the latest CSF assessment and build the csf_score run-ai payload.

    Raises the same typed 404/409s run-ai does (no assessment / locked / not
    seeded) so preview and run-ai agree on when a run is even possible. Reads
    only — never mutates.
    """
    a = _latest_assessment(db, svc.id)
    if a is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Create an assessment first."
        )
    if a.status in (CsfAssessmentStatus.APPROVED, CsfAssessmentStatus.RELEASED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This assessment is locked."
        )
    rows = {
        f"{r.tier}|{r.subcategory_code}": r
        for r in db.execute(
            select(CsfDimensionScore).where(CsfDimensionScore.assessment_id == a.id)
        )
        .scalars()
        .all()
    }
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seed the Working Profile before running AI.",
        )
    locked_keys = frozenset(k for k, r in rows.items() if r.locked)

    # Ground the suggestion in the client's interview answers + evidence flags,
    # the way ZT's run-ai does (routes/zt.py). Only answers with actual signal
    # are sent (a scored tier, notes, or attached evidence) so the model sees
    # what the analyst captured rather than ~106 empty rows. The payload goes
    # through the redactor (nested note strings included) as designed.
    answer_rows = (
        db.execute(select(CsfAnswer).where(CsfAnswer.assessment_id == a.id)).scalars().all()
    )
    answers = {
        ans.subcategory_code: {
            "maturity_tier": ans.maturity_tier,
            "notes": ans.notes,
            "has_evidence": ans.evidence_artifact_id is not None,
        }
        for ans in answer_rows
        if ans.maturity_tier is not None or ans.notes or ans.evidence_artifact_id is not None
    }
    client_org = None if client.legal_name == "(pending intake)" else client.legal_name
    return CsfAiRequest(
        assessment=a,
        rows=rows,
        locked_keys=locked_keys,
        preview=AiPreviewPayload(
            job_name="csf_score",
            inputs={
                "tiers": sorted({r.tier for r in rows.values()}),
                "subcategories": sorted({r.subcategory_code for r in rows.values()}),
                "answers": answers,
            },
            client_org_name=client_org,
        ),
    )


@router.post(
    "/services/{service_id}/run-ai",
    response_model=CsfRunAiResponse,
    summary="Run the csf_score AI job: suggest dimension scores + narrative (admin)",
)
def run_ai(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
    llm: Annotated[LLMClient, Depends(_llm_dep)],
    _rl: Annotated[None, Depends(enforce_ai_rate_limit)],
) -> CsfRunAiResponse:
    """The CSF full-Playbook 'Run AI'. Suggests the five dimension scores (0-2)
    + a 'what we found' narrative per (tier, subcategory). AI suggests; locked
    rows are untouched; code does the total/level/cap + Enterprise roll-up.
    Returns a 'what changed' list.
    """
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
    req = build_csf_ai_request(db, svc, client)
    a, rows, locked_keys = req.assessment, req.rows, req.locked_keys

    def _snap() -> dict[str, dict]:
        return {k: {f: getattr(r, f) for f in _RUN_FIELDS} for k, r in rows.items()}

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
    data = result.data if isinstance(result.data, dict) else {}

    for sugg in data.get("scores", []):
        if not isinstance(sugg, dict):
            continue
        row = rows.get(f"{sugg.get('tier')}|{sugg.get('subcategory_code')}")
        if row is None or row.locked:
            continue
        for dim in _DIM_FIELDS:
            if dim in sugg:
                try:
                    v = int(sugg[dim])
                except (TypeError, ValueError):
                    continue
                if 0 <= v <= 2:
                    setattr(row, dim, v)
        if isinstance(sugg.get("what_we_found"), str):
            row.what_we_found = sugg["what_we_found"]

    db.flush()
    after = _snap()
    diffs = diff_keyed_rows(before, after, list(_RUN_FIELDS), locked_keys=locked_keys)
    if not diffs:
        # FAIL LOUDLY: a run that parsed but changed nothing is the exact
        # symptom of the T0 schema-drift bug (a compliant response silently
        # discarded). Surface it — a re-run that suggests identical values also
        # trips this, which is still worth a "did this do anything?" signal.
        _log.warning(
            "csf_run_ai_no_changes",
            service_id=str(svc.id),
            assessment_id=str(a.id),
            suggestions=len(data.get("scores", [])),
            unlocked_rows=len(rows) - len(locked_keys),
        )
    changes: list[CsfDimensionChange] = []
    for d in diffs:
        tier, _, code = d.key.partition("|")
        for ch in d.changes:
            changes.append(
                CsfDimensionChange(
                    tier=tier, subcategory_code=code, field=ch.field, old=ch.old, new=ch.new
                )
            )

    # D-031 concurrency: a discard racing this run must win. Re-read the parent
    # status before committing so suggestions never land in a discarded (or
    # newly locked) assessment.
    current_status = db.execute(
        select(CsfAssessment.status).where(CsfAssessment.id == a.id)
    ).scalar_one()
    if current_status in (
        CsfAssessmentStatus.DISCARDED,
        CsfAssessmentStatus.APPROVED,
        CsfAssessmentStatus.RELEASED,
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
        action="csf.run_ai",
        target_type="csf_assessment",
        target_id=a.id,
        actor_user_id=user.id,
        details={"changed_rows": len(diffs)},
    )
    db.commit()
    out_rows = [
        _score_response(r)
        for r in sorted(rows.values(), key=lambda r: (r.tier, r.subcategory_code))
    ]
    return CsfRunAiResponse(changed=changes, rows=out_rows)


@router.post(
    "/services/{service_id}/playbook/export",
    response_model=CsfPlaybookExportResponse,
    summary="Render + store the CSF full-Playbook workbook (XLSX) (admin)",
)
def export_playbook(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(_storage_dep)],
) -> CsfPlaybookExportResponse:
    """An Enterprise Profile sheet (weighted-floor roll-up) + one sheet per tier
    with the five dimension scores and computed total/level/cap."""
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
    a = _latest_assessment(db, svc.id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No assessment yet.")
    all_rows = (
        db.execute(select(CsfDimensionScore).where(CsfDimensionScore.assessment_id == a.id))
        .scalars()
        .all()
    )
    if not all_rows:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seed the Working Profile before exporting.",
        )
    enterprise_rows, _ = _enterprise_subcategories(db, a)
    gap_actions = _load_gap_actions(db, a.id)
    tier_profiles: dict[str, list] = {}
    for tier in ("high", "moderate", "low"):
        trows = sorted(
            (r for r in all_rows if r.tier == tier),
            key=lambda r: r.subcategory_code,
        )
        if trows:
            tier_profiles[tier] = [_score_response(r) for r in trows]

    from app.docx_export import DOCX_MIME

    org = None if client.legal_name == "(pending intake)" else client.legal_name
    name = org or "Client"
    today = utcnow().date()
    on = utcnow().strftime("%Y-%m-%d")
    xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    pdf_mime = "application/pdf"

    def _pb_name(extension: str, variant: str | None = None) -> str:
        # §15.5: {Company}_CSF_Playbook{MMDDYY}[_v{n}][_variant].ext
        return deliverable_filename(
            company=org,
            service_slug=SERVICE_SLUG_CSF_PLAYBOOK,
            extension=extension,
            day=today,
            version=a.version,
            variant=variant,
        )

    specs = [
        (
            "xlsx",
            "Data workbook (XLSX)",
            _pb_name("xlsx"),
            xlsx_mime,
            csf_playbook_export.render_xlsx(
                client_name=name,
                version=a.version,
                enterprise_rows=enterprise_rows,
                tier_profiles=tier_profiles,
                gap_actions=gap_actions,
            ),
        ),
        (
            "exec_pdf",
            "Executive briefing (PDF)",
            _pb_name("pdf", "Executive"),
            pdf_mime,
            csf_playbook_export.render_exec_pdf(
                client_name=name,
                version=a.version,
                enterprise_rows=enterprise_rows,
                generated_on=on,
            ),
        ),
        (
            "exec_docx",
            "Executive briefing (Word)",
            _pb_name("docx", "Executive"),
            DOCX_MIME,
            csf_playbook_export.render_exec_docx(
                client_name=name,
                version=a.version,
                enterprise_rows=enterprise_rows,
                generated_on=on,
            ),
        ),
        (
            "full_pdf",
            "Full playbook (PDF)",
            _pb_name("pdf", "Full"),
            pdf_mime,
            csf_playbook_export.render_full_pdf(
                client_name=name,
                version=a.version,
                enterprise_rows=enterprise_rows,
                generated_on=on,
            ),
        ),
        (
            "full_docx",
            "Full playbook (Word)",
            _pb_name("docx", "Full"),
            DOCX_MIME,
            csf_playbook_export.render_full_docx(
                client_name=name,
                version=a.version,
                enterprise_rows=enterprise_rows,
                generated_on=on,
            ),
        ),
    ]
    artifacts: list[ExportedArtifact] = []
    for kind, label, filename, mime, data in specs:
        art = _write_artifact(
            db,
            storage=storage,
            user=user,
            client_id=client.id,
            filename=filename,
            mime_type=mime,
            data=data,
        )
        artifacts.append(
            ExportedArtifact(kind=kind, label=label, artifact_id=art.id, filename=art.title)
        )

    audit(
        db,
        action="csf.playbook_exported",
        target_type="csf_assessment",
        target_id=a.id,
        actor_user_id=user.id,
        details={"version": a.version, "artifacts": len(artifacts)},
    )
    a.documents_stale = False  # Work Order C3: exporting refreshes the documents
    db.commit()
    return CsfPlaybookExportResponse(artifacts=artifacts)


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
        stage="csf.deliverable",
        uploaded_by=user.id,
    )
    db.add(art)
    db.flush()
    return art


@router.post(
    "/services/{service_id}/deliverables/finalize",
    response_model=DeliverableResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Render PDF + XLSX deliverable from the latest approved CSF assessment (admin)",
)
def finalize_csf_deliverable(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(_storage_dep)],
) -> DeliverableResponse:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
    assessment = _latest_assessment(db, svc.id)
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No assessment yet.",
        )
    if assessment.status not in (
        CsfAssessmentStatus.APPROVED,
        CsfAssessmentStatus.RELEASED,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment must be approved before finalizing the deliverable.",
        )
    answers = (
        db.execute(select(CsfAnswer).where(CsfAnswer.assessment_id == assessment.id))
        .scalars()
        .all()
    )
    valid = all_codes()
    tier_map: dict[str, int | None] = {
        r.subcategory_code: r.maturity_tier for r in answers if r.subcategory_code in valid
    }
    notes_map: dict[str, str | None] = {
        r.subcategory_code: r.notes for r in answers if r.subcategory_code in valid
    }
    score = compute_score(tier_map)
    gap = analyze_gaps(tier_map, notes=notes_map)

    client_name = client.legal_name
    if client_name == "(pending intake)":
        client_name = None

    # Filename version: same-day re-finalize -> v2, v3, ...
    today = utcnow().date()
    existing_count = db.execute(select(Deliverable).where(Deliverable.service_id == svc.id)).all()
    next_version = len(existing_count) + 1

    pdf_name = deliverable_filename(
        company=client_name,
        service_slug=SERVICE_SLUG_NIST_CSF,
        extension="pdf",
        day=today,
        version=next_version,
    )
    xlsx_name = deliverable_filename(
        company=client_name,
        service_slug=SERVICE_SLUG_NIST_CSF,
        extension="xlsx",
        day=today,
        version=next_version,
    )
    docx_name = deliverable_filename(
        company=client_name,
        service_slug=SERVICE_SLUG_NIST_CSF,
        extension="docx",
        day=today,
        version=next_version,
    )

    ctx = build_csf_context(
        client_legal_name=client_name,
        service_title=svc.title,
        assessment=assessment,
        answers=answers,
        score=score,
        gap=gap,
    )
    pdf_bytes = render_csf_pdf(ctx)
    xlsx_bytes = render_csf_xlsx(ctx)
    docx_bytes = render_csf_docx(ctx)

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
        f"Overall maturity: {score.overall_maturity_label}. "
        f"{score.answered_subcategories}/{score.total_subcategories} subcategories scored; "
        f"{gap.total_gap_count} gap(s) at target T{gap.target_tier}."
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
        action="csf.deliverable.finalized",
        target_type="deliverable",
        target_id=deliv.id,
        actor_user_id=user.id,
        details={
            "service_id": str(svc.id),
            "assessment_id": str(assessment.id),
            "assessment_version": assessment.version,
            "version": next_version,
            "overall_maturity_label": score.overall_maturity_label,
            "average_tier": score.average_tier,
            "coverage_pct": score.coverage_pct,
            "gap_count": gap.total_gap_count,
        },
    )
    assessment.documents_stale = False  # Work Order C3
    db.commit()
    db.refresh(deliv)
    return _serialize_deliverable(db, deliv)


@router.get(
    "/services/{service_id}/deliverables/latest",
    response_model=DeliverableResponse,
    summary="Most recent CSF deliverable for a service (admin)",
)
def latest_csf_deliverable(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> DeliverableResponse:
    # Deliverables are admin-only (Work Order A1): clients never see or
    # download them in-app.
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
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
    summary="Release a finalized CSF deliverable to the client (admin, D-025)",
)
def release_csf_deliverable(
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
        kinds=(ServiceKind.NIST_CSF,),
        action="csf.deliverable.released",
    )
    return _serialize_deliverable(db, deliv)

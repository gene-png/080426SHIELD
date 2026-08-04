"""Tech Debt service routes (Master Spec §15 Phase 3).

This stage (Phase 3 stage 4) ships the spine:
  - POST /tech-debt/services         (open a service workspace; admin-only)
  - POST /tech-debt/services/{id}/capability-lists/extract
        (run the AI extraction; produces a new versioned CapabilityList)
  - GET  /tech-debt/services/{id}/capability-lists/latest

The editable extraction table (PATCH per item, approve list) lands in
stage 5; overlap analysis in stage 6; consolidation plan in stage 7;
deliverable render in stage 8; client release in stage 9.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.ai.llm import LLMClient
from app.audit import audit
from app.db.session import get_db
from app.deliverable_release import release_deliverable
from app.dependencies import current_client, current_user, require_role
from app.logging import get_logger
from app.models._common import utcnow
from app.models.artifact import Artifact, ArtifactOrigin
from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
from app.models.client import Client
from app.models.deliverable import Deliverable
from app.models.service import Service, ServiceKind, ServiceStatus
from app.models.user import User, UserRole
from app.routes.artifacts import _storage_dep
from app.schemas.tech_debt import (
    CapabilityItemPatch,
    CapabilityItemResponse,
    CapabilityListResponse,
    ConsolidationPlanSummary,
    DeliverableResponse,
    ExtractRequest,
    OverlapAnalysisResponse,
    OverlapBucketResponse,
    ServiceCreateRequest,
    ServiceResponse,
    TopCostItemResponse,
)
from app.security.rate_limit import enforce_ai_rate_limit
from app.storage import StorageBackend
from app.tech_debt.exporters import build_context, render_docx, render_pdf, render_xlsx
from app.tech_debt.extract import (
    client_org_name_for_tenant,
    extract_capabilities,
    name_hints_for_tenant,
)
from app.tech_debt.filename import (
    SERVICE_SLUG_BY_KIND,
    deliverable_filename,
)
from app.tech_debt.overlap import analyze_overlap
from app.tech_debt.parsers import SUPPORTED_MIME, UnsupportedInventoryFormat
from app.tenant import (
    require_artifact_in_tenant,
    require_service_in_tenant,
)

router = APIRouter(prefix="/tech-debt", tags=["tech-debt"])

_admin_required = Depends(require_role(UserRole.ADMIN))

_log = get_logger(__name__)


# Module-level slot for tests + production. Tests inject a FixtureProvider-
# backed client via FastAPI dependency overrides; production gets the
# settings-built client lazily.
def _llm_dep() -> LLMClient:
    return LLMClient.from_settings()


@router.post(
    "/services",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Open a service workspace (admin)",
)
def create_service(
    body: ServiceCreateRequest,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> ServiceResponse:
    svc = Service(
        kind=body.kind,
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
        action="service.opened",
        target_type="service",
        target_id=svc.id,
        actor_user_id=user.id,
        details={
            "kind": body.kind.value,
            "source_request_id": str(body.source_request_id) if body.source_request_id else None,
        },
    )
    db.commit()
    db.refresh(svc)
    return ServiceResponse.model_validate(svc, from_attributes=True)


def _latest_list_or_none(db: Session, service_id: uuid.UUID) -> CapabilityList | None:
    # D-031: a DISCARDED list is retired from every "latest" consumer (GET
    # latest, the draft-reuse guard, deliverable finalize). The next-version
    # mint deliberately does NOT use this helper - see _max_list_version.
    return db.execute(
        select(CapabilityList)
        .where(
            CapabilityList.service_id == service_id,
            CapabilityList.status != CapabilityListStatus.DISCARDED,
        )
        .order_by(CapabilityList.version.desc())
        .limit(1)
    ).scalar_one_or_none()


def _max_list_version(db: Session, service_id: uuid.UUID) -> int:
    """Highest version across ALL lists, discarded included (D-031 version trap).

    The (service_id, version) unique constraint counts discarded rows, so the
    next mint must step past the true max - not past the latest non-discarded
    version, which would collide when a non-v1 draft was discarded.
    """
    return (
        db.execute(
            select(func.max(CapabilityList.version)).where(CapabilityList.service_id == service_id)
        ).scalar()
        or 0
    )


def _serialize_list_with_items(db: Session, cap_list: CapabilityList) -> CapabilityListResponse:
    items = (
        db.execute(select(CapabilityItem).where(CapabilityItem.capability_list_id == cap_list.id))
        .scalars()
        .all()
    )
    return CapabilityListResponse(
        id=cap_list.id,
        service_id=cap_list.service_id,
        version=cap_list.version,
        status=cap_list.status,
        items=[CapabilityItemResponse.model_validate(i, from_attributes=True) for i in items],
        approved_at=cap_list.approved_at,
        approved_by=cap_list.approved_by,
    )


@router.post(
    "/services/{service_id}/capability-lists/extract",
    response_model=CapabilityListResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Extract capability list from an inventory artifact (admin)",
)
def extract_capability_list(
    service_id: uuid.UUID,
    body: ExtractRequest,
    response: Response,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(_storage_dep)],
    llm: Annotated[LLMClient, Depends(_llm_dep)],
    _rl: Annotated[None, Depends(enforce_ai_rate_limit)],
) -> CapabilityListResponse:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.TECH_DEBT)
    artifact = require_artifact_in_tenant(db, body.artifact_id, client.id)
    if artifact.mime_type not in SUPPORTED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(f"Inventory MIME {artifact.mime_type!r} is not supported. " "Use CSV or XLSX."),
        )

    # Draft-exists guard (Sprint 8 T1, ported from CSF / ATT&CK / Zero Trust):
    # this route used to mint a new version and fire a fresh LLM extraction on
    # EVERY call, so a double-click on "extract" produced unbounded v2, v3, v4…
    # drafts and burned an AI call per click. The guard sits AFTER service/
    # artifact validation but BEFORE extract_capabilities() so a second POST
    # while a draft is open does NOT invoke the LLM. If an unsubmitted draft is
    # already open, return it idempotently (HTTP 200) untouched — NO
    # re-extraction, NO clear-and-repopulate, so consultant edits/locks on the
    # open draft survive. A new version is only cut once the prior list has
    # moved on (approved/released). A POST with a different artifact_id while a
    # draft is open still returns that open draft (documented contract; an
    # explicit replace/re-extract affordance is a future candidate).
    existing = _latest_list_or_none(db, svc.id)
    if existing is not None and existing.status == CapabilityListStatus.DRAFT:
        _log.info(
            "techdebt_reused_open_draft",
            list_id=str(existing.id),
            version=existing.version,
            service_id=str(svc.id),
        )
        response.status_code = status.HTTP_200_OK
        return _serialize_list_with_items(db, existing)

    try:
        result = extract_capabilities(
            db=db,
            storage=storage,
            artifact=artifact,
            requested_by=user,
            service_id=svc.id,
            client_id=client.id,
            client_org_name=client_org_name_for_tenant(db, client.id),
            name_hints=name_hints_for_tenant(db, client.id),
            llm=llm,
        )
    except UnsupportedInventoryFormat as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        # LLM returned unparseable JSON. The llm_calls row is already
        # written; surface a 502 so the admin sees this is upstream, not
        # client error.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI extraction failed to parse: {exc}",
        ) from exc

    # Determine next version off the true max (discarded rows still hold their
    # version under the unique constraint - D-031 version trap).
    next_version = _max_list_version(db, svc.id) + 1
    cap_list = CapabilityList(service_id=svc.id, version=next_version)
    db.add(cap_list)
    db.flush()

    for item in result.items:
        db.add(
            CapabilityItem(
                capability_list_id=cap_list.id,
                name=item.name,
                vendor=item.vendor,
                category=item.category,
                function=item.function,
                annual_cost_usd=item.annual_cost_usd,
                license_count=item.license_count,
                notes=item.notes,
                confidence_pct=item.confidence_pct,
                source_artifact_id=artifact.id,
            )
        )

    audit(
        db,
        action="capability_list.extracted",
        target_type="capability_list",
        target_id=cap_list.id,
        actor_user_id=user.id,
        details={
            "service_id": str(svc.id),
            "version": next_version,
            "artifact_id": str(artifact.id),
            "item_count": len(result.items),
            "llm_call_id": str(result.llm_call.id),
        },
    )
    db.commit()
    db.refresh(cap_list)
    return _serialize_list_with_items(db, cap_list)


@router.get(
    "/services/{service_id}/capability-lists/latest",
    response_model=CapabilityListResponse,
    summary="Most recent capability list for a service",
)
def latest_capability_list(
    service_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CapabilityListResponse:
    svc = require_service_in_tenant(db, service_id, client.id)
    cap_list = _latest_list_or_none(db, svc.id)
    if cap_list is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No capability list yet. Run extraction first.",
        )
    # Phase 3 admin-only for now; client view of the released deliverable
    # comes in stage 9 via /deliverables/.
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Capability lists are admin-only until release.",
        )
    return _serialize_list_with_items(db, cap_list)


@router.patch(
    "/capability-items/{item_id}",
    response_model=CapabilityItemResponse,
    summary="Inline-edit a single capability item (admin)",
)
def patch_capability_item(
    item_id: uuid.UUID,
    body: CapabilityItemPatch,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CapabilityItemResponse:
    item = db.get(CapabilityItem, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Capability item not found.",
        )
    # Refuse edits to items that belong to a released list.
    cap_list = db.get(CapabilityList, item.capability_list_id)
    # Tenant check via parent service.
    if cap_list is not None:
        svc = db.get(Service, cap_list.service_id)
        if svc is None or svc.client_id != client.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Capability item not found.",
            )
    # A released OR discarded parent is not editable (D-031: a stale tab must
    # not write into a list the admin already discarded).
    if cap_list is not None and cap_list.status in (
        CapabilityListStatus.RELEASED,
        CapabilityListStatus.DISCARDED,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This capability list has been released and is locked."
                if cap_list.status == CapabilityListStatus.RELEASED
                else "This capability list has been discarded."
            ),
        )

    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Patch body is empty.",
        )
    # Lock/unlock is a meta-action handled separately so a NULL never reaches
    # the NOT NULL column and so it doesn't clear AI confidence on its own.
    locked_val = data.pop("locked", None)
    for field, value in data.items():
        setattr(item, field, value)
    if data:
        # A content edit -> no longer an AI guess.
        item.confidence_pct = None
    if locked_val is not None:
        item.locked = bool(locked_val)

    audit(
        db,
        action="capability_item.edited",
        target_type="capability_item",
        target_id=item.id,
        actor_user_id=user.id,
        details={
            "fields": sorted(data.keys()),
            "capability_list_id": str(item.capability_list_id),
        },
    )
    db.commit()
    db.refresh(item)
    return CapabilityItemResponse.model_validate(item, from_attributes=True)


@router.post(
    "/capability-lists/{list_id}/approve",
    response_model=CapabilityListResponse,
    summary="Approve a capability list (admin)",
)
def approve_capability_list(
    list_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CapabilityListResponse:
    cap_list = db.get(CapabilityList, list_id)
    if cap_list is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Capability list not found.",
        )
    svc = db.get(Service, cap_list.service_id)
    if svc is None or svc.client_id != client.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Capability list not found.",
        )
    if cap_list.status == CapabilityListStatus.RELEASED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This capability list has been released and is locked.",
        )
    cap_list.status = CapabilityListStatus.APPROVED
    cap_list.approved_at = utcnow()
    cap_list.approved_by = user.id
    audit(
        db,
        action="capability_list.approved",
        target_type="capability_list",
        target_id=cap_list.id,
        actor_user_id=user.id,
        details={"service_id": str(cap_list.service_id), "version": cap_list.version},
    )
    db.commit()
    db.refresh(cap_list)
    return _serialize_list_with_items(db, cap_list)


@router.post(
    "/capability-lists/{list_id}/discard",
    response_model=CapabilityListResponse,
    summary="Discard a draft capability list (admin, D-031)",
)
def discard_capability_list(
    list_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CapabilityListResponse:
    """Soft-delete an unapproved draft. Only a DRAFT is discardable; re-discard
    is idempotent (no second audit row); approved/released -> typed 409. The
    write is a conditional UPDATE ... WHERE status='draft' so two racing
    transactions cannot both observe DRAFT and proceed (D-031 concurrency
    contract). Uploaded intake artifacts survive - re-extraction is the point."""
    cap_list = db.get(CapabilityList, list_id)
    if cap_list is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Capability list not found."
        )
    svc = db.get(Service, cap_list.service_id)
    if svc is None or svc.client_id != client.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Capability list not found."
        )
    if cap_list.status == CapabilityListStatus.DISCARDED:
        return _serialize_list_with_items(db, cap_list)  # idempotent, no audit
    if cap_list.status != CapabilityListStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "not_discardable",
                "message": "Only a draft capability list can be discarded.",
            },
        )
    item_count = db.execute(
        select(func.count())
        .select_from(CapabilityItem)
        .where(CapabilityItem.capability_list_id == cap_list.id)
    ).scalar_one()
    result = db.execute(
        update(CapabilityList)
        .where(
            CapabilityList.id == cap_list.id,
            CapabilityList.status == CapabilityListStatus.DRAFT,
        )
        .values(status=CapabilityListStatus.DISCARDED)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.refresh(cap_list)
        if cap_list.status == CapabilityListStatus.DISCARDED:
            return _serialize_list_with_items(db, cap_list)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "not_discardable",
                "message": "Only a draft capability list can be discarded.",
            },
        )
    audit(
        db,
        action="capability_list.discarded",
        target_type="capability_list",
        target_id=cap_list.id,
        actor_user_id=user.id,
        details={
            "service_id": str(cap_list.service_id),
            "version": cap_list.version,
            "item_count": item_count,
        },
    )
    _log.info(
        "techdebt_discarded_draft",
        list_id=str(cap_list.id),
        version=cap_list.version,
        service_id=str(cap_list.service_id),
        item_count=item_count,
    )
    db.commit()
    db.refresh(cap_list)
    return _serialize_list_with_items(db, cap_list)


@router.get(
    "/services/{service_id}/overlap-analysis",
    response_model=OverlapAnalysisResponse,
    summary="Overlap analysis for the latest capability list (admin)",
)
def overlap_analysis(
    service_id: uuid.UUID,
    _user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> OverlapAnalysisResponse:
    svc = require_service_in_tenant(db, service_id, client.id)
    cap_list = _latest_list_or_none(db, svc.id)
    if cap_list is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No capability list yet. Run extraction first.",
        )
    items = (
        db.execute(select(CapabilityItem).where(CapabilityItem.capability_list_id == cap_list.id))
        .scalars()
        .all()
    )
    analysis = analyze_overlap(list(items))

    def _bucket(b) -> OverlapBucketResponse:
        return OverlapBucketResponse(
            key=b.key,
            item_count=b.item_count,
            total_cost=b.total_cost,
            cost_known=b.cost_known,
            item_ids=[uuid.UUID(i) for i in b.item_ids],
            item_names=list(b.item_names),
        )

    return OverlapAnalysisResponse(
        capability_list_id=cap_list.id,
        capability_list_version=cap_list.version,
        by_category=[_bucket(b) for b in analysis.by_category],
        by_vendor=[_bucket(b) for b in analysis.by_vendor],
        top_cost_items=[
            TopCostItemResponse(
                id=uuid.UUID(i.id),
                name=i.name,
                vendor=i.vendor,
                category=i.category,
                annual_cost_usd=i.annual_cost_usd,
            )
            for i in analysis.top_cost_items
        ],
        total_cost=analysis.total_cost,
        total_items=analysis.total_items,
        uncategorized_count=analysis.uncategorized_count,
        no_vendor_count=analysis.no_vendor_count,
        no_cost_count=analysis.no_cost_count,
    )


@router.get(
    "/services/{service_id}/consolidation-plan",
    response_model=ConsolidationPlanSummary,
    summary="Consolidation-plan summary for the latest capability list (admin)",
)
def consolidation_plan_summary(
    service_id: uuid.UUID,
    _user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> ConsolidationPlanSummary:
    from app.models.capability import CapabilityDisposition

    svc = require_service_in_tenant(db, service_id, client.id)
    cap_list = _latest_list_or_none(db, svc.id)
    if cap_list is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No capability list yet. Run extraction first.",
        )
    items = (
        db.execute(select(CapabilityItem).where(CapabilityItem.capability_list_id == cap_list.id))
        .scalars()
        .all()
    )

    keep = 0
    consolidate = 0
    cut = 0
    undecided = 0
    cut_savings = 0.0
    savings_cost_known = True
    for it in items:
        if it.disposition is None:
            undecided += 1
            continue
        if it.disposition == CapabilityDisposition.KEEP:
            keep += 1
        elif it.disposition == CapabilityDisposition.CONSOLIDATE:
            consolidate += 1
        elif it.disposition == CapabilityDisposition.CUT:
            cut += 1
            if it.annual_cost_usd is None:
                savings_cost_known = False
            else:
                cut_savings += float(it.annual_cost_usd)

    return ConsolidationPlanSummary(
        capability_list_id=cap_list.id,
        capability_list_version=cap_list.version,
        total_items=len(items),
        keep_count=keep,
        consolidate_count=consolidate,
        cut_count=cut,
        undecided_count=undecided,
        estimated_annual_savings=cut_savings,
        savings_cost_known=savings_cost_known,
    )


# ---------------------------------------------------------------------------
# Deliverable workflow (Phase 3 stage 8)
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
        stage="tech_debt.deliverable",
        uploaded_by=user.id,
    )
    db.add(art)
    db.flush()
    return art


@router.post(
    "/services/{service_id}/deliverables/finalize",
    response_model=DeliverableResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Render PDF + XLSX deliverable from the latest approved capability list (admin)",
)
def finalize_deliverable(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(_storage_dep)],
) -> DeliverableResponse:
    svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.TECH_DEBT)
    cap_list = _latest_list_or_none(db, svc.id)
    if cap_list is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No capability list yet.",
        )
    if cap_list.status != CapabilityListStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Capability list must be approved before finalizing the deliverable.",
        )
    items = (
        db.execute(select(CapabilityItem).where(CapabilityItem.capability_list_id == cap_list.id))
        .scalars()
        .all()
    )

    client_name = client.legal_name
    if client_name == "(pending intake)":
        client_name = None

    # Filename version: same-day re-finalize -> v2, v3, ...
    today = utcnow().date()
    existing_count = db.execute(select(Deliverable).where(Deliverable.service_id == svc.id)).all()
    next_version = len(existing_count) + 1

    service_slug = SERVICE_SLUG_BY_KIND.get(svc.kind.value, "Tech_Debt_Review")
    pdf_name = deliverable_filename(
        company=client_name,
        service_slug=service_slug,
        extension="pdf",
        day=today,
        version=next_version,
    )
    xlsx_name = deliverable_filename(
        company=client_name,
        service_slug=service_slug,
        extension="xlsx",
        day=today,
        version=next_version,
    )
    docx_name = deliverable_filename(
        company=client_name,
        service_slug=service_slug,
        extension="docx",
        day=today,
        version=next_version,
    )

    ctx = build_context(
        client_legal_name=client_name,
        service_title=svc.title,
        cap_list=cap_list,
        items=items,
    )
    pdf_bytes = render_pdf(ctx)
    xlsx_bytes = render_xlsx(ctx)
    docx_bytes = render_docx(ctx)

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
        mime_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
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
        f"{len(items)} capabilities reviewed; "
        f"{'≥ ' if not ctx.savings_cost_known else ''}"
        f"${ctx.estimated_savings:,.0f} estimated annual savings."
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
        action="deliverable.finalized",
        target_type="deliverable",
        target_id=deliv.id,
        actor_user_id=user.id,
        details={
            "service_id": str(svc.id),
            "capability_list_id": str(cap_list.id),
            "capability_list_version": cap_list.version,
            "version": next_version,
            "pdf_artifact_id": str(pdf_artifact.id),
            "xlsx_artifact_id": str(xlsx_artifact.id),
            "estimated_annual_savings": ctx.estimated_savings,
            "savings_cost_known": ctx.savings_cost_known,
        },
    )
    db.commit()
    db.refresh(deliv)
    return _serialize_deliverable(db, deliv)


@router.get(
    "/services/{service_id}/deliverables/latest",
    response_model=DeliverableResponse,
    summary="Most recent deliverable for a service (admin)",
)
def latest_deliverable(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> DeliverableResponse:
    # Deliverables are admin-only (Work Order A1): clients never see or
    # download them in-app.
    svc = require_service_in_tenant(db, service_id, client.id)
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
    summary="Release a finalized Tech Debt deliverable to the client (admin, D-025)",
)
def release_tech_debt_deliverable(
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
        kinds=(ServiceKind.TECH_DEBT,),
        action="tech_debt.deliverable.released",
    )
    return _serialize_deliverable(db, deliv)

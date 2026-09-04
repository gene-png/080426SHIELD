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
    CapabilityComponentsRequest,
    CapabilityItemPatch,
    CapabilityItemResponse,
    CapabilityListResponse,
    ConsolidationPlanSummary,
    DeliverableResponse,
    ExtractRequest,
    IncludeExcludedRowRequest,
    OverlapAnalysisResponse,
    OverlapBucketResponse,
    SecurityClassificationOverride,
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
from app.tech_debt.security_scope import security_scope_filter
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
def _llm_dep(db: Annotated[Session, Depends(get_db)]) -> LLMClient:
    """Issue 2: build from the DB so a key an admin pasted at runtime is
    honoured on the very next Run-AI, with no redeploy."""
    return LLMClient.from_db(db)


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


def approved_membership_stale(db: Session, cap_list: CapabilityList) -> bool:
    """True when the approved snapshot no longer matches current security scope.

    W3 froze allow-list membership at approval so a post-approval edit could not
    silently rewrite what a citation was "confirmed against" (#32). The snapshot
    is deliberately NOT auto-refreshed — silently ADDING an unreviewed row to a
    hard allow-list is the defect #32 records.

    But the same silence cuts the other way, and that half was missed:
    `override_security_classification` exists to undo a wrong non-security call,
    and its own docstring promises such a row "must not keep a stale sign-off
    that would silently re-exclude it". Once the list is approved, the snapshot
    re-excluded it anyway, one layer up — so a tool the consultant just restored
    could not be cited, and every technique it covers came back a fabricated gap.
    `add_capability_components` has the same shape: decomposing an approved
    bundle produced children invisible to the mapping, which is the exact
    regression that feature was built to fix.

    Auto-refreshing would trade #32's defect back. Refusing the edit would break
    two first-class workflows. So the list REPORTS that its approved membership
    is out of date, and re-approval remains the one deliberate, audited way to
    change what the model may cite. Silence in either direction is the thing to
    avoid.
    """
    if cap_list.approved_membership is None:
        return False

    # Compare NAME AND VENDOR. W2 made the vendor load-bearing — the citation
    # resolver uses it to decide whether a cited string is unambiguous — and
    # `patch_capability_item` can edit `vendor` on an approved list. Comparing
    # names only meant correcting a vendor left the list reporting "not stale",
    # so nothing prompted a re-approval and the resolver kept resolving against
    # the old vendor indefinitely.
    #
    # Snapshots written between W3 and W2 carry no `vendor` key. `.get` yields
    # None for those, which matches a row whose vendor is genuinely blank and
    # differs from one that has a vendor — so such a list reads as stale exactly
    # when the vendor column would change a resolution, which is the point.
    def _key(name: object, vendor: object) -> tuple[str, str | None]:
        return ((str(name or "")).strip(), (str(vendor or "")).strip() or None)

    approved = {
        _key(e.get("name"), e.get("vendor"))
        for e in cap_list.approved_membership
        if (e.get("name") or "").strip()
    }
    current = {
        _key(n, v)
        for n, v in db.execute(
            select(CapabilityItem.name, CapabilityItem.vendor).where(
                CapabilityItem.capability_list_id == cap_list.id,
                security_scope_filter(),
            )
        ).all()
        if (n or "").strip()
    }
    return approved != current


def _serialize_list_with_items(db: Session, cap_list: CapabilityList) -> CapabilityListResponse:
    items = (
        db.execute(select(CapabilityItem).where(CapabilityItem.capability_list_id == cap_list.id))
        .scalars()
        .all()
    )
    # Built FROM THE MODEL, not field-by-field. The hand-written version silently
    # dropped a newly-added column twice — `source_rows_total`, then `confirmed`
    # — each time reading as null in the UI with nothing failing. A new column on
    # CapabilityList now flows through automatically; only `items` is filled by
    # hand, because it is a separate query rather than an attribute.
    resp = CapabilityListResponse.model_validate(cap_list, from_attributes=True)
    resp.items = [CapabilityItemResponse.model_validate(i, from_attributes=True) for i in items]
    resp.approved_membership_stale = approved_membership_stale(db, cap_list)
    return resp


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
    cap_list = CapabilityList(
        service_id=svc.id,
        version=next_version,
        # Persisted so the disclosure survives a page reload: the workspace
        # re-fetches the list on every load, and a warning that vanishes on
        # refresh is no warning (UX finding 4).
        source_rows_total=result.reconciliation.received,
        excluded_rows=[
            {"index": e.index, "summary": e.summary} for e in result.reconciliation.excluded_rows
        ],
    )
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
                # Prompt v2 classifies rather than filters. None stays None: an
                # unclassified row is not a negative one.
                security_related=item.security_related,
                security_functions=list(item.security_functions),
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


def _editable_list_or_404(db: Session, list_id: uuid.UUID, client: Client) -> CapabilityList:
    """Fetch a capability list in this tenant that is still open to edits."""
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
    if cap_list.status in (
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
    return cap_list


def _excluded_entry_or_404(cap_list: CapabilityList, row_index: int) -> dict:
    for entry in cap_list.excluded_rows or []:
        if int(entry.get("index", -1)) == row_index:
            return entry
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="That row is not in this list's excluded rows.",
    )


@router.post(
    "/capability-lists/{list_id}/excluded-rows/{row_index}/include",
    response_model=CapabilityListResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Include a row the extraction skipped (admin)",
)
def include_excluded_row(
    list_id: uuid.UUID,
    row_index: int,
    body: IncludeExcludedRowRequest,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CapabilityListResponse:
    """Recover a row the extractor wrongly skipped (UX finding 4).

    Disclosure told the consultant nine rows were dropped; this is how they act
    on it. The consultant supplies the values — the raw row is free text the
    extractor already declined to interpret, so re-parsing it here would be
    guessing at exactly the point a human has stepped in.
    """
    cap_list = _editable_list_or_404(db, list_id, client)
    entry = _excluded_entry_or_404(cap_list, row_index)

    item = CapabilityItem(
        capability_list_id=cap_list.id,
        name=body.name,
        vendor=body.vendor,
        category=body.category,
        function=body.function,
        annual_cost_usd=body.annual_cost_usd,
        license_count=body.license_count,
        notes=body.notes,
        # Human-added, so it carries no AI confidence badge.
        confidence_pct=None,
    )
    db.add(item)
    # It is no longer excluded: dropping it keeps `received = included +
    # excluded` true, which is the whole point of the reconciliation.
    cap_list.excluded_rows = [
        e for e in (cap_list.excluded_rows or []) if int(e.get("index", -1)) != row_index
    ]
    audit(
        db,
        action="capability_list.excluded_row_included",
        target_type="capability_list",
        target_id=cap_list.id,
        actor_user_id=user.id,
        details={"row_index": row_index, "name": body.name, "summary": entry.get("summary")},
    )
    db.commit()
    db.refresh(cap_list)
    return _serialize_list_with_items(db, cap_list)


@router.post(
    "/capability-lists/{list_id}/excluded-rows/{row_index}/confirm",
    response_model=CapabilityListResponse,
    summary="Confirm a row was correctly excluded (admin)",
)
def confirm_excluded_row(
    list_id: uuid.UUID,
    row_index: int,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CapabilityListResponse:
    """Acknowledge an exclusion as correct.

    The row STAYS listed — the reconciliation has to keep telling the truth
    about what was uploaded — but the workspace can stop flagging it as
    outstanding.
    """
    cap_list = _editable_list_or_404(db, list_id, client)
    _excluded_entry_or_404(cap_list, row_index)

    # Rebuild the list: a JSON column mutated in place is not seen as dirty.
    cap_list.excluded_rows = [
        (
            {**e, "confirmed": True}
            if int(e.get("index", -1)) == row_index
            else {"confirmed": False, **e}
        )
        for e in (cap_list.excluded_rows or [])
    ]
    audit(
        db,
        action="capability_list.excluded_row_confirmed",
        target_type="capability_list",
        target_id=cap_list.id,
        actor_user_id=user.id,
        details={"row_index": row_index},
    )
    db.commit()
    db.refresh(cap_list)
    return _serialize_list_with_items(db, cap_list)


def _editable_item_or_404(
    db: Session, item_id: uuid.UUID, client: Client
) -> tuple[CapabilityItem, CapabilityList]:
    """Fetch an item in this tenant whose list is still open to edits."""
    item = db.get(CapabilityItem, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Capability item not found.",
        )
    cap_list = _editable_list_or_404(db, item.capability_list_id, client)
    return item, cap_list


@router.post(
    "/capability-items/{item_id}/security-classification/confirm",
    response_model=CapabilityListResponse,
    summary="Agree a capability is not security-related (admin)",
)
def confirm_security_classification(
    item_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CapabilityListResponse:
    """Sign off on a NEGATIVE security classification.

    Until this runs, the model's "not security-related" call is provisional and
    the row stays in the ATT&CK subset (app.tech_debt.security_scope). This is
    the only thing that takes it out, and it takes a human to do it — a wrongly
    dropped security tool becomes uncitable in the mapping, so its absence would
    read as an assessed gap rather than a missing input.

    Only meaningful on a negative. Confirming a row the model called
    security-related would record agreement with a classification that has no
    effect, so it is refused rather than silently stored.
    """
    item, cap_list = _editable_item_or_404(db, item_id, client)
    if item.security_related is not False:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "not_a_negative_classification",
                "message": (
                    "Only a capability classified as not security-related needs "
                    "sign-off. This one is not."
                ),
            },
        )

    item.security_class_confirmed = True
    audit(
        db,
        action="capability_item.security_classification_confirmed",
        target_type="capability_item",
        target_id=item.id,
        actor_user_id=user.id,
        details={"name": item.name},
    )
    db.commit()
    db.refresh(cap_list)
    return _serialize_list_with_items(db, cap_list)


@router.post(
    "/capability-items/{item_id}/security-classification/override",
    response_model=CapabilityListResponse,
    summary="Overturn a classification: this capability IS security-related (admin)",
)
def override_security_classification(
    item_id: uuid.UUID,
    body: SecurityClassificationOverride,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CapabilityListResponse:
    """Record that the model got the security call wrong.

    The consultant supplies which of prevent / detect / respond it serves; the
    model is not re-asked. Clearing `security_class_confirmed` matters on the
    path back — a row confirmed non-security and later overturned must not keep
    a stale sign-off that would silently re-exclude it if it were reclassified.
    """
    item, cap_list = _editable_item_or_404(db, item_id, client)

    item.security_related = True
    item.security_functions = [f.value for f in body.security_functions]
    item.security_class_confirmed = False
    audit(
        db,
        action="capability_item.security_classification_overridden",
        target_type="capability_item",
        target_id=item.id,
        actor_user_id=user.id,
        details={"name": item.name, "security_functions": item.security_functions},
    )
    db.commit()
    db.refresh(cap_list)
    return _serialize_list_with_items(db, cap_list)


@router.post(
    "/capability-items/{item_id}/components",
    response_model=CapabilityListResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Name the capabilities inside a bundled licence (admin)",
)
def add_capability_components(
    item_id: uuid.UUID,
    body: CapabilityComponentsRequest,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> CapabilityListResponse:
    """Expand one bundled row into the capabilities it contains.

    UX finding 5 / E2E F-6: "Microsoft 365 E5" extracted as a single $294,120
    line, so the Defender / Entra components that overlap the client's separately
    licensed CrowdStrike, Proofpoint and Okta were invisible to redundancy
    analysis and to the ATT&CK tool mapping.

    The CONSULTANT names the components. The model is never asked what is inside
    a bundle — that would be fabricated detail, which is exactly what the AI seam
    exists to prevent.

    Components carry no cost: the parent keeps the whole licence value, so
    decomposing can never inflate the portfolio total.
    """
    item = db.get(CapabilityItem, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Capability item not found.",
        )
    cap_list = db.get(CapabilityList, item.capability_list_id)
    if cap_list is not None:
        svc = db.get(Service, cap_list.service_id)
        if svc is None or svc.client_id != client.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Capability item not found.",
            )
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
    # One level only: a component of a component has no real-world counterpart
    # here and would make the cost story ambiguous.
    if item.parent_item_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "component_cannot_be_split",
                "message": (
                    "This is already a component of a bundle. Split the bundle "
                    "itself, not one of its parts."
                ),
            },
        )

    for comp in body.components:
        db.add(
            CapabilityItem(
                capability_list_id=item.capability_list_id,
                parent_item_id=item.id,
                name=comp.name,
                vendor=item.vendor,
                category=comp.category,
                function=comp.function,
                # No cost: the parent holds the licence value.
                annual_cost_usd=None,
                license_count=None,
                notes=comp.notes,
                # Human-named, so no AI confidence badge.
                confidence_pct=None,
                source_artifact_id=item.source_artifact_id,
            )
        )
    audit(
        db,
        action="capability_item.components_added",
        target_type="capability_item",
        target_id=item.id,
        actor_user_id=user.id,
        details={"count": len(body.components)},
    )
    db.commit()
    db.refresh(item)
    return _serialize_list_with_items(db, db.get(CapabilityList, item.capability_list_id))


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


def build_approved_membership(db: Session, capability_list_id: uuid.UUID) -> list[dict]:
    """The D-053 snapshot: WHAT was approved, not merely that approval happened.

    Extracted from `approve_capability_list` so it is callable without a request,
    a user or a tenant -- which is what lets the ATT&CK enrichment tests seed a
    snapshot through the REAL writer instead of hand-writing its shape. A test
    that hand-writes the snapshot agrees with the reader by construction: rename
    `item_id` here and every such test stays green while the live join silently
    returns nothing and every tool loses its description.

    `vendor` is in here (W2) because the citation resolver uses it to judge
    whether a cited string is unambiguous, so a vendor edited after approval
    would move the allow-list exactly the way a name edit does.
    """
    return [
        {"item_id": str(i.id), "name": i.name, "vendor": i.vendor}
        for i in db.execute(
            select(CapabilityItem)
            .where(CapabilityItem.capability_list_id == capability_list_id)
            .where(security_scope_filter())
            .order_by(CapabilityItem.name)
        )
        .scalars()
        .all()
    ]


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
    # W3: record WHAT was approved, not merely that approval happened.
    #
    # An APPROVED list stays editable until release — `_editable_list_or_404`
    # blocks RELEASED and DISCARDED only — through five doors, one of which
    # (`patch_capability_item`) can change `name`, and one of which (the
    # security-classification confirm queue) changes allow-list membership BY
    # DESIGN. `attack.py::_client_tool_names` turns these names into a hard
    # allow-list, so without this every "confirmed against the approved list"
    # claim was checked against whatever the list had since become.
    #
    # Re-approval overwrites deliberately: editing an approved list is a real
    # workflow, and the fix is to make the change explicit and audited rather
    # than to forbid it.
    membership = build_approved_membership(db, cap_list.id)
    previous = cap_list.approved_membership
    cap_list.approved_membership = membership
    audit(
        db,
        action="capability_list.approved",
        target_type="capability_list",
        target_id=cap_list.id,
        actor_user_id=user.id,
        details={
            "service_id": str(cap_list.service_id),
            "version": cap_list.version,
            # The count alone is uninterpretable on a RE-approval — "12" says
            # nothing about whether the allow-list just changed. `replaced` is
            # what distinguishes a first approval from one that overwrote an
            # earlier membership (D-049's lesson, applied here).
            "approved_membership_count": len(membership),
            "replaced_membership_count": len(previous) if previous is not None else None,
        },
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
    # RELEASED counts as approved-or-better, matching csf/zt/attack. This was
    # `!= APPROVED`, which was harmless only while nothing ever assigned
    # RELEASED: once W4 flips the parent on release, `!= APPROVED` would make
    # releasing a tech-debt deliverable permanently block finalizing any further
    # version for that service. CI could not have caught it — the only spec
    # covering release-then-finalize (`s17-documents`) runs on CSF, which already
    # accepted RELEASED. The ATT&CK plan's claim that all four services
    # "hard-gate finalize on APPROVED/RELEASED" was false here, and only here.
    if cap_list.status not in (
        CapabilityListStatus.APPROVED,
        CapabilityListStatus.RELEASED,
    ):
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
        # W4: the parent version this report was built from. Stamped here, at the
        # freeze, because this is where the content is fixed against a specific
        # parent and where that parent is already required to be APPROVED.
        # Release reads it to flip exactly this row (migration 0041).
        parent_version=cap_list.version,
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

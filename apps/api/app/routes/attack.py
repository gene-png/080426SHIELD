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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.ai.diff import diff_keyed_rows
from app.ai.engine import get_job, run_job
from app.ai.failures import ai_call_boundary
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
from app.attack.citations import (
    _MAX_REJECTED_EXAMPLES,
    Candidate,
    CitationOutcome,
    CitationResolver,
    resolve_citations,
)
from app.attack.coverage import COVERAGE_DEFINITIONS, CoverageStatus
from app.attack.exporters import build_context as build_attack_context
from app.attack.exporters import render_docx as render_attack_docx
from app.attack.exporters import render_pdf as render_attack_pdf
from app.attack.exporters import render_xlsx as render_attack_xlsx
from app.attack.pending import CLAIMS_SUPPORT as _STATUS_CLAIMS_SUPPORT
from app.attack.pending import NO_CITATION as _NO_CITATION
from app.attack.pending import TOOL_FIELDS as _TOOL_FIELDS
from app.attack.pending import confirm_all as confirm_attack_citations
from app.attack.pending import pending_codes as attack_pending_codes
from app.attack.pending import row_tools as attack_row_tools
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
from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
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
from app.tech_debt.security_scope import security_scope_filter
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
    """Every coverage row on the wire goes through here.

    This used to name each field by hand, and `patch_coverage` did the same
    thing a second time. Adding `unconfirmed_citations` (#101) to the schema and
    to `run_ai` therefore left BOTH of these still returning `null` for it -- and
    because `pending_review` is derived from that field, the omission did not
    read as a missing field, it read as "every technique is pending review".

    `model_validate(..., from_attributes=True)` is what `run_ai` already used and
    is why `run_ai` was the one path that worked. Three copies of a field list is
    the twins problem CLAUDE.md keeps recording; one construction has no twin to
    forget.
    """
    return [
        AttackCoverageResponse.model_validate(r, from_attributes=True)
        for r in sorted(rows, key=lambda r: r.technique_code)
    ]


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
    # Admin-only, unconditionally — matching `tech_debt.py`'s capability-list
    # read (W4 / D-046). This was `role != ADMIN and status != RELEASED`, which
    # returned 403 to every client for the route's entire life because nothing
    # outside the seed script ever assigned RELEASED. W4 makes that status
    # reachable, so the old form would have started serving clients the raw
    # assessment: per-technique `notes`, `evidence_artifact_id`, `locked` and
    # `answered_by`. ATT&CK has NO client-input step, so every one of those notes
    # is consultant-authored internal text and `answered_by` is an internal user
    # id. The client's purpose-built view (`clients.py`'s attack dashboard) emits
    # only status, rationale and the tool lists — it omits exactly those four
    # fields, deliberately.
    #
    # NOTE the asymmetry with `csf.py` and `zt.py`, which keep the
    # release-conditional form. It is DELIBERATE, not an oversight to tidy up:
    # both are client-input services and expose the identical serialization
    # through an ungated `GET .../self-assessment` ("the client owns these
    # answers"), so tightening those two would close a door with an open one
    # beside it and imply a protection that does not exist. Whether a client
    # should see a released ATT&CK assessment at all, and through which view, is
    # a policy question filed separately rather than decided by a status fix.
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ATT&CK assessments are admin-only.",
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
    # #102. Setting the status or curating the tools by hand makes the ADMIN the
    # author of this row's claim, not a reviewer of the model's -- so the model's
    # outstanding inferences and rejections stop being what the claim rests on,
    # and are stamped as vouched for. 5.1's second definition of "confirmed" is
    # exactly this: a human cleared it.
    #
    # Scoped to those four fields on purpose. Editing `notes`, `rationale`,
    # `locked` or the evidence pointer says nothing about whether a cited tool
    # name was the right one, and clearing a review queue as a side effect of a
    # typo fix would be a silent loss of the disclosure.
    #
    # Entries are stamped, never deleted: "a human accepted this" and "nobody
    # ever cited it" are different answers to why a technique counts.
    authored = {"status", "detection_tools", "prevention_tools", "response_tools"} & set(data)
    if authored:
        before_uncleared = len(row.unconfirmed_citations or []) - sum(
            1 for e in (row.unconfirmed_citations or []) if e.get("cleared_at") is not None
        )
        row.unconfirmed_citations = confirm_attack_citations(
            row.unconfirmed_citations, at=utcnow().isoformat()
        )
        _log.info(
            "attack.coverage.citations_confirmed_by_hand",
            coverage_id=str(row.id),
            technique_code=row.technique_code,
            fields=sorted(authored),
            cleared=before_uncleared,
        )
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
            # Recorded because this is the one path that CLEARS a review queue,
            # and "why does this technique count now" has to be answerable later
            # from the audit trail rather than from the row's current state.
            "citations_confirmed_by_hand": len(row.unconfirmed_citations or []) if authored else 0,
        },
    )
    db.commit()
    db.refresh(row)
    # The second of the two hand-built copies this response used to have. See
    # `_serialize_coverage` for why neither is hand-built any more.
    return AttackCoverageResponse.model_validate(row, from_attributes=True)


def _llm_dep(db: Annotated[Session, Depends(get_db)]) -> LLMClient:
    """Issue 2: build from the DB so a key an admin pasted at runtime is
    honoured on the very next Run-AI, with no redeploy."""
    return LLMClient.from_db(db)


def _client_capabilities(db: Session, client_id: uuid.UUID) -> list[Candidate]:
    """Security capabilities from the client's Tech Debt capability list(s).

    Returns name AND vendor: the citation resolver needs the vendor column to
    judge whether a cited string is unambiguous, and a MISSING vendor is itself
    information — it makes a vendor-shaped match unverifiable rather than false.

    ATT&CK maps the client's security tooling to techniques; the canonical
    source is the Tech Debt capability list (Work Order D2).

    Two filters, both load-bearing:

    * **Security scope.** Tech Debt covers the whole software portfolio since
      migration 0038, so the raw list now includes payroll and CRM. Only rows in
      security scope are offered here — and `security_scope_filter` deliberately
      keeps rows whose non-security call is unconfirmed, because this list is a
      hard allow-list on what the model may cite: a tool missing from it cannot
      be named, and the technique it covers reads as uncovered.
    * **List status.** Previously absent entirely, so a DISCARDED list's rows
      stayed citable forever — a consultant throwing a draft away did not stop
      its tools being offered as evidence. Only DISCARDED is excluded here:
      DRAFT still counts, because mapping ATT&CK before approving the tech-debt
      list is a normal order of work. Superseded versions also still count,
      which is arguably wrong but is pre-existing behaviour and not this
      change's business.
    * **Approved membership (W3).** For a list that has been approved, the
      APPROVED SNAPSHOT is the membership, not the live rows. An approved list
      stays editable until release — `_editable_list_or_404` blocks RELEASED and
      DISCARDED only — and two of those doors change what this function returns:
      `patch_capability_item` can rename an item, and the security-classification
      confirm queue removes a row from security scope BY DESIGN. Reading live
      rows meant a citation "confirmed against the approved list" was checked
      against whatever the list had since become, which is the premise #32
      recorded as deferred and W2's narrow-confirmed would otherwise rest on.
      The snapshot also carries the VENDOR (W2): the citation resolver uses it
      to judge whether a cited string is unambiguous, so a vendor edited after
      approval would move the allow-list exactly the way a name edit does.
      A list with no recorded membership (a DRAFT, or one approved before
      migration 0043) still reads live — NULL means nobody recorded it, which is
      not the same as nothing having been approved.
    """
    lists = (
        db.execute(
            select(CapabilityList)
            .join(Service, CapabilityList.service_id == Service.id)
            .where(
                Service.client_id == client_id,
                Service.kind == ServiceKind.TECH_DEBT,
                CapabilityList.status != CapabilityListStatus.DISCARDED,
            )
        )
        .scalars()
        .all()
    )

    pairs: list[tuple[str, str | None]] = []
    # Lists whose approved membership was never recorded still read live: a DRAFT
    # by design (mapping ATT&CK before approving the tech-debt list is a normal
    # order of work, per the docstring above), and a pre-0043 list because NULL
    # means "nobody recorded this", which is not the same as "nothing was
    # approved" — the C0 pattern. Inventing a membership for those would assert
    # something no consultant ever did.
    # `is None`, NOT falsy. An approved list with ZERO in-scope items stores
    # `[]`, and `not []` is True — so under the falsy test that list fell back to
    # reading LIVE rows, which is the one case where #32's hole stayed open. The
    # model docstring and this one both say the rule is NULL; the falsy spelling
    # did not implement it. Pinned by
    # `test_an_empty_snapshot_is_not_the_same_as_no_snapshot`, because `not x` is
    # exactly the simplification a reviewer would suggest back.
    live_ids = [cl.id for cl in lists if cl.approved_membership is None]
    for cap_list in lists:
        # W3: for an APPROVED list the snapshot IS the membership. The list stays
        # editable until release through five doors — one of which can rename an
        # item, and one of which (the confirm queue) removes a row from security
        # scope by design — so reading live rows here meant every "confirmed
        # against the approved list" citation was checked against whatever the
        # list had since become.
        if cap_list.approved_membership is not None:
            pairs.extend(
                # A snapshot written before W2 carries no `vendor` key. Reading
                # that as UNKNOWN rather than as "no vendor" is the cautious
                # direction: the resolver flags a vendor-shaped match it cannot
                # verify instead of resolving it confidently.
                (e.get("name") or "", e.get("vendor"))
                for e in cap_list.approved_membership
            )

    if live_ids:
        pairs.extend(
            db.execute(
                select(CapabilityItem.name, CapabilityItem.vendor).where(
                    CapabilityItem.capability_list_id.in_(live_ids),
                    security_scope_filter(),
                )
            ).all()
        )

    # De-duplicate on the NAME, keeping the first vendor seen for it. Two lists
    # can carry the same tool; emitting it twice would make every citation of it
    # ambiguous and reject every one of them.
    # Dedupe CASE-INSENSITIVELY, not on the exact string.
    #
    # Two lists for one client can hold `Splunk` and `SPLUNK` — one extracted
    # from an all-caps table. Deduping on the exact string kept both, which made
    # `_by_norm["splunk"]` hold two names, so the resolver called the citation
    # ambiguous and REJECTED it. `main` collapsed the pair via
    # `frozenset(t.lower() ...)` and kept the citation, so that would have been a
    # regression: the client loses evidence they used to get, and the panel tells
    # the consultant the tool "is not on the list" when it is on it twice.
    #
    # Sorted so the winner is deterministic. The query has no ORDER BY, and
    # picking by row order meant the same inputs could resolve differently
    # between runs when two lists disagreed about a vendor.
    by_key: dict[str, tuple[str, str | None]] = {}
    for name, vendor in sorted(pairs, key=lambda p: (p[0] or "", p[1] or "")):
        clean = (name or "").strip()
        if not clean:
            continue
        key = clean.casefold()
        clean_vendor = (vendor or "").strip() or None
        if key not in by_key:
            by_key[key] = (clean, clean_vendor)
        elif by_key[key][1] is None and clean_vendor is not None:
            # Prefer a spelling that carries a vendor — a vendor-less duplicate
            # would make every vendor-shaped citation unverifiable for no reason.
            by_key[key] = (by_key[key][0], clean_vendor)
    return [Candidate(name=n, vendor=v) for n, v in sorted(by_key.values())]


def _client_tool_names(db: Session, client_id: uuid.UUID) -> list[str]:
    """Just the names, for callers that only need allow-list membership."""
    return [c.name for c in _client_capabilities(db, client_id)]


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
    # W2: the same allow-list carrying vendors, for the citation resolver. A
    # near miss used to be dropped SILENTLY by the exact-match filter, so a
    # technique the client covers read as a gap — or kept a `covered` status
    # with an empty tool list.
    capabilities: list[Candidate]
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

    capabilities = _client_capabilities(db, client.id)
    tools = [c.name for c in capabilities]
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
        capabilities=capabilities,
        preview=AiPreviewPayload(
            job_name="mitre_map",
            inputs={"capability_list": tools, "technique_codes": sorted(rows)},
            client_org_name=client_org,
        ),
    )


# mitre_map asks for one JSON object per ATT&CK technique, and the Enterprise
# matrix supplies ~633 of them. Measured live on 2026-08-07 it costs ~575 output
# tokens per technique, so a single request wants ~364k output tokens — 2.8x
# claude-opus-5's 128k ceiling — and ~80 minutes of generation. It is not a
# budget problem; one request cannot express this job. It is split.
#
# 25 keeps a batch near ~14k output tokens: comfortably inside every provider's
# ceiling, ~30s of generation, and small enough that losing one costs little.
# Batches run concurrently because wall-clock here is dominated by token
# throughput, which batching alone does not improve — only overlapping does.
# 5 workers is deliberately modest: the provider rate limit is shared with every
# other job in the deployment, and this endpoint already sits behind
# enforce_ai_rate_limit.
_MITRE_BATCH_SIZE = 25
_MITRE_MAX_WORKERS = 5


@dataclass
class _BatchedResult:
    """Shape-compatible stand-in for engine.JobResult's `.data`."""

    data: dict[str, Any]


def _run_mitre_map_batched(
    db: Session,
    llm: LLMClient,
    req: AttackAiRequest,
    *,
    requested_by: uuid.UUID,
    service_id: uuid.UUID,
    client_id: uuid.UUID,
) -> tuple[list[dict], int, int]:
    """Run mitre_map as concurrent batches. Returns (suggestions, total, failed).

    Each batch is a real `run_job` call and therefore writes its own `llm_calls`
    row — N rows per run instead of one. That is the honest accounting: N
    provider calls were made and each is separately billable.

    Each worker gets its OWN Session. A SQLAlchemy Session is not thread-safe,
    and the request-scoped `db` belongs to the endpoint; sharing it across
    threads corrupts state. Each worker commits its own audit row so evidence of
    a call survives independently of whether its siblings — or the request —
    succeed.

    A partial failure does NOT discard the run. Losing 1 batch of 26 should cost
    the consultant 25 techniques, not all 633 and the money already spent on
    them. Only a total failure raises, and it raises through `ai_call_boundary`
    so the error stays typed and carries `charged_likely`.
    """
    codes = [c for c in (req.preview.inputs.get("technique_codes") or []) if isinstance(c, str)]
    batches = [
        codes[i : i + _MITRE_BATCH_SIZE] for i in range(0, len(codes), _MITRE_BATCH_SIZE)
    ] or [[]]

    def _one(batch: list[str]) -> dict:
        # Bind to the REQUEST session's engine, not the module-level
        # SessionLocal. A Session is not thread-safe so each worker needs its
        # own, but reaching for SessionLocal opens a connection outside whatever
        # the caller is bound to — which silently bypassed the test suite's
        # dependency-injected engine and broke isolation across test files.
        # get_bind() keeps workers on the same database the request is using.
        session = Session(bind=db.get_bind())
        try:
            out = run_job(
                session,
                llm,
                req.preview.job_name,
                inputs={**req.preview.inputs, "technique_codes": batch},
                requested_by=requested_by,
                service_id=service_id,
                client_id=client_id,
                client_org_name=req.preview.client_org_name,
                name_hints=req.preview.name_hints,
            )
            session.commit()
            # Guaranteed a dict by `parse_json_object`; a wrong shape raises
            # and is counted as a failed batch rather than a silent empty one.
            return out.data
        except Exception:
            # Mirror ai_call_boundary: commit so the FAILED row survives the
            # exception, then let it propagate to be counted.
            session.commit()
            raise
        finally:
            session.close()

    # Warm the job registry on THIS thread before any worker touches it. Lazy
    # registration behind a module flag is not something a worker should be the
    # first to trigger, even now that the flag ordering is fixed.
    get_job(req.preview.job_name)

    suggestions: list[dict] = []
    failed = 0
    first_error: Exception | None = None

    with ThreadPoolExecutor(max_workers=_MITRE_MAX_WORKERS) as pool:
        futures = [pool.submit(_one, b) for b in batches]
        for fut in as_completed(futures):
            try:
                data = fut.result()
            except Exception as exc:  # noqa: BLE001 - counted, not swallowed
                failed += 1
                first_error = first_error or exc
                _log.error(
                    "mitre_map_batch_failed",
                    service_id=str(service_id),
                    error=f"{type(exc).__name__}: {exc}",
                )
                continue
            suggestions.extend(t for t in (data.get("techniques") or []) if isinstance(t, dict))

    if failed == len(batches) and first_error is not None:
        # Nothing usable came back. Re-raise inside the boundary so the caller
        # gets the same typed 502 + charged_likely it always did.
        with ai_call_boundary(db, llm, purpose=req.preview.job_name):
            raise first_error

    return suggestions, len(batches), failed


@router.post(
    "/coverage/{coverage_id}/confirm-citations",
    response_model=AttackCoverageResponse,
    summary="Vouch for a technique's inferred citations so its status may score (admin)",
)
def confirm_coverage_citations(
    coverage_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> AttackCoverageResponse:
    """5.1's second definition of CONFIRMED: a human cleared it (#101 / #102).

    #101's complaint was that "queued for a human" was neither queued nor
    retrievable. Persisting the flags answered the second half; this answers the
    first -- a queue a consultant cannot work through is a list, not a queue.

    Deliberately separate from `patch_coverage`, which also clears a row's
    outstanding entries. The two say different things and both are worth being
    able to read back out of the audit trail later: confirming says *the model's
    inference was correct*, patching a status says *here is my own answer*. Only
    the first is a review of what the AI did.

    It does NOT touch `status` or the tool lists. The claim is unchanged; what
    changes is that its evidence now has a human behind it.
    """
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
        # Same guard as every other write to a coverage row. Clearing a queue
        # RAISES coverage, so allowing it after sign-off would change a delivered
        # figure without a new version.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This assessment is locked.",
        )
    outstanding = [e for e in (row.unconfirmed_citations or []) if e.get("cleared_at") is None]
    if not outstanding:
        # Refused rather than returned as a cheerful no-op. A 200 here would write
        # an audit row putting this user's name against a review that did not
        # happen, which is the same class of untruth as a ledger row recording a
        # success above the commit that makes it true.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "nothing_to_confirm",
                "message": (
                    "This technique has no citations awaiting review. Either they were "
                    "already confirmed, or nothing about this row was ever inferred."
                ),
            },
        )
    row.unconfirmed_citations = confirm_attack_citations(
        row.unconfirmed_citations, at=utcnow().isoformat()
    )
    audit(
        db,
        action="attack.coverage.citations_confirmed",
        target_type="attack_coverage",
        target_id=row.id,
        actor_user_id=user.id,
        details={
            "technique_code": row.technique_code,
            "confirmed": len(outstanding),
            # The names as well as the count: "why does this technique count" is
            # answered by WHICH inference a human accepted, not by how many.
            "tools": sorted({e.get("tool") for e in outstanding if e.get("tool")}),
            "reasons": sorted({e.get("reason") for e in outstanding if e.get("reason")}),
        },
    )
    db.commit()
    db.refresh(row)
    _log.info(
        "attack.coverage.citations_confirmed",
        coverage_id=str(row.id),
        technique_code=row.technique_code,
        confirmed=len(outstanding),
    )
    return AttackCoverageResponse.model_validate(row, from_attributes=True)


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
    a, rows, locked_keys = (
        req.assessment,
        req.rows,
        req.locked_keys,
    )
    # `req.valid_tools` is no longer consulted: the resolver owns matching now,
    # and an exact-match frozenset beside it would be a second, laxer answer to
    # the same question. The field stays on the request because the preview
    # payload and its tests read it.
    resolver = CitationResolver(req.capabilities)
    citations = CitationOutcome()
    tools = req.preview.inputs["capability_list"]

    # An empty allow-list cannot produce an assessment — only a fabricated one.
    # `valid_tools` is a HARD allow-list (see `_client_tool_names`): a tool that
    # is not in it cannot be cited, so with zero tools every technique can only
    # come back uncovered no matter what the client actually runs.
    #
    # This is not hypothetical. A live run on 2026-08-07 with tools_available=0
    # wrote 607 `gap` + 26 `not_applicable` across all 633 techniques, billed for
    # the call, and left a releasable assessment stating a catastrophic security
    # posture that was an artifact of missing input. The audit row recorded
    # `tools_available: 0`, so the system knew; the only disclosure was a
    # post-run sentence, after the money was spent and the rows were written.
    #
    # Refuse before spending anything, and name the actual remedy — the usual
    # cause is that the Tech Debt work was done under a DIFFERENT client, and
    # tenant isolation (correctly) will not reach across for it.
    if not tools:
        _log.warning(
            "attack.run_ai.refused_no_capabilities",
            service_id=str(svc.id),
            client_id=str(client.id),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "no_security_capabilities",
                "message": (
                    "This client has no security capabilities to map against, so "
                    "every technique would be reported as a gap regardless of what "
                    "the client actually runs. Complete this client's Tech Debt "
                    "capability list first — if you already did, check it was done "
                    "under this client and not another one."
                ),
            },
        )

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
    suggestions, batches_total, batches_failed = _run_mitre_map_batched(
        db,
        llm,
        req,
        requested_by=user.id,
        service_id=svc.id,
        client_id=client.id,
    )
    result = _BatchedResult(data={"techniques": suggestions})

    def _validate_tools(names: object, field: str, row_flags: list[dict]) -> list[str]:
        """Resolve the cited names against the allow-list, and ACCOUNT for each.

        This was `t.lower() in valid_tools` â€” exact match, and every near miss
        dropped silently with no count and no reason. The technique kept
        whatever status the model gave it, so a citation that missed by a word
        left a `covered` technique with an empty tool list, or a `gap` on a
        control the client owns. A fabricated gap is the failure N-033 shipped.

        Accumulates into the run-level `citations` outcome so the numbers reach
        the consultant instead of a log line nobody reads.
        """
        out = resolve_citations(names, resolver)
        citations.confirmed += out.confirmed
        citations.needs_review += out.needs_review
        citations.rejected += out.rejected
        for tool in out.needs_review_tools:
            if tool not in citations.needs_review_tools:
                citations.needs_review_tools.append(tool)
        citations.unusable += out.unusable
        for reason, tools_for in out.needs_review_by_reason.items():
            bucket = citations.needs_review_by_reason.setdefault(reason, [])
            for tool in tools_for:
                if tool not in bucket:
                    bucket.append(tool)
        for example in out.rejected_examples:
            if (
                len(citations.rejected_examples) < _MAX_REJECTED_EXAMPLES
                and example not in citations.rejected_examples
            ):
                citations.rejected_examples.append(example)
        # #101: the same outcomes, per ROW, so they outlive the response. The
        # run-level lists above are a summary a consultant reads once; these are
        # the queue they work through, and until migration 0044 they existed only
        # in React state.
        #
        # REJECTIONS are recorded as well as inferences, with `tool: None`. A
        # rejected citation applies no tool, so at first glance there is nothing
        # to store -- but without it a row whose every citation was dropped is
        # byte-identical to a row nobody ever cited anything for, and #102 has to
        # withhold the first while leaving the second alone. See
        # `app/attack/pending.py`.
        for entry in out.inferred:
            row_flags.append({**entry, "field": field, "cleared_at": None})
        for entry in out.rejected_details:
            row_flags.append({"tool": None, **entry, "field": field, "cleared_at": None})
        return out.tools

    for sugg in (result.data or {}).get("techniques", []):
        if not isinstance(sugg, dict):
            continue
        row = rows.get(sugg.get("technique_code"))
        if row is None or row.locked:
            continue
        st = sugg.get("status")
        if isinstance(st, str) and st in _VALID_STATUSES:
            row.status = st
        # #101 / #102: record what happened to this row's citations, per FIELD.
        #
        # `row_flags` starts EMPTY, not None. An empty list is a positive claim --
        # "the resolver looked and nothing is outstanding" -- and NULL is reserved
        # for rows nobody ever resolved, which score as pending. The two are not
        # interchangeable; see migration 0044.
        #
        # A re-resolved field REPLACES its own entries, `cleared_at` stamps
        # included. A clearance is a human vouching for one inference; a new run
        # is a new set of inferences, and carrying the stamp across by matching
        # (tool, field, reason) would be inferring that the judgement still
        # applies -- inference is exactly what is not confirmation here. It costs
        # re-review after a rerun, and the plan's tiebreak spends that: "an
        # understated coverage number is a conservative claim a consultant can
        # raise after review; an overstated one is a false assurance already
        # delivered to a client."
        #
        # A field the model did NOT send keeps both its tools and its entries.
        # See the block below the loop for why that is not symmetry-for-its-own-
        # sake.
        row_flags: list[dict] = []
        resolved_fields: set[str] = set()
        for tool_field in _TOOL_FIELDS:
            if tool_field in sugg:
                setattr(row, tool_field, _validate_tools(sugg[tool_field], tool_field, row_flags))
                resolved_fields.add(tool_field)

        # PER-FIELD, not per-row. `row.<field>` is only overwritten for the
        # fields the model actually sent, so a rerun that omits one leaves that
        # field's tools in place -- and replacing the whole citation record would
        # then say "resolved, nothing outstanding" about tools this run never
        # looked at. A row withheld for an inferred `response_tools` citation
        # would flip to scoring because a later run happened to re-resolve
        # `detection_tools`, with no human anywhere in the loop.
        #
        # That is this change's own guard turning into the fail-open it was
        # written to close, which CLAUDE.md records twice: "a guard against
        # DOUBLE-counting will quietly become a guard against counting at all."
        prior = row.unconfirmed_citations
        # `no_citation` (field None) is a ROW-level marker, so it has no field to
        # be scoped by and is never carried -- it is re-derived below from what
        # this run actually left behind. Carrying it would leave the panel saying
        # no tool was named while a tool sits in the Detection row above it.
        carried = [
            e
            for e in (prior or [])
            if e.get("field") is not None and e.get("field") not in resolved_fields
        ]

        # Fields this run did not resolve, that hold tools nothing on record
        # accounts for. While the column is NULL those tools were never checked
        # at all, so the row cannot be described as resolved yet -- writing any
        # list would be the fail-closed-to-fail-open flip one step further out.
        unaccounted = [
            f for f in _TOOL_FIELDS if f not in resolved_fields and getattr(row, f, None)
        ]
        if prior is not None or not unaccounted:
            merged = carried + row_flags
            # A positive claim with nothing cited for it anywhere. Not a rejection
            # (nothing was named) and not an inference (nothing was resolved), so
            # neither loop above emits anything -- and an empty list here would say
            # "resolved, nothing outstanding", which is the answer a HAND-CURATED
            # row gets and the one thing this row must not be confused with.
            # Record the omission where it happens.
            if row.status in _STATUS_CLAIMS_SUPPORT and not merged and not attack_row_tools(row):
                merged.append(
                    {
                        "tool": None,
                        "cited": None,
                        "reason": _NO_CITATION,
                        "field": None,
                        "cleared_at": None,
                    }
                )
            row.unconfirmed_citations = merged
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
    # Computed HERE, below the D-031 re-read that decides this run is allowed to
    # land at all. CLAUDE.md: a record that says "this happened" belongs after
    # the guard that makes it true, or it eventually asserts something the
    # database does not contain -- W1's accounting log claimed `applied=N` above
    # this same re-read and reported values applied for transactions that then
    # rolled back.
    pending = attack_pending_codes(rows.values())
    _log.info(
        "attack.run_ai.citations_resolved",
        service_id=str(svc.id),
        confirmed=citations.confirmed,
        needs_review=citations.needs_review,
        rejected=citations.rejected,
        unusable=citations.unusable,
        pending_review_rows=len(pending),
    )
    audit(
        db,
        action="attack.run_ai",
        target_type="attack_assessment",
        target_id=a.id,
        actor_user_id=user.id,
        details={
            "tools_available": len(tools),
            "changed_rows": len(diffs),
            # #102. The audit row is where "why did coverage drop" gets answered
            # months later, and the citation numbers were only ever in a response
            # nobody keeps.
            "citations_confirmed": citations.confirmed,
            "citations_needs_review": citations.needs_review,
            "citations_rejected": citations.rejected,
            "pending_review_rows": len(pending),
        },
    )
    db.commit()

    coverage = [
        AttackCoverageResponse.model_validate(r, from_attributes=True)
        for r in sorted(rows.values(), key=lambda r: r.technique_code)
    ]
    return AttackRunAiResponse(
        tools_available=len(tools),
        changed=changes,
        coverage=coverage,
        batches_total=batches_total,
        batches_failed=batches_failed,
        citations_confirmed=citations.confirmed,
        citations_needs_review=citations.needs_review,
        citations_rejected=citations.rejected,
        citations_rejected_examples=list(citations.rejected_examples),
        citations_needs_review_tools=list(citations.needs_review_tools),
        citations_needs_review_by_reason={
            k: list(v) for k, v in citations.needs_review_by_reason.items()
        },
        citations_unusable=citations.unusable,
        pending_review_rows=len(pending),
    )


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
    rollup = compute_heatmap(coverage_map, attack_pending_codes(rows))
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
        pending_review=rollup.pending_review,
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
                pending_review=tc.pending_review,
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
    # The SAME derivation the heatmap uses. The PDF is the surface that reaches
    # the client, so a deliverable computed off an un-withheld rollup would be
    # the one place the whole rule does not apply -- which is the only place it
    # has to.
    rollup = compute_heatmap(coverage_map, attack_pending_codes(coverage))

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
        # W4: the parent version this report was built from. Stamped here, at the
        # freeze, because this is where the content is fixed against a specific
        # parent and where that parent is already required to be APPROVED.
        # Release reads it to flip exactly this row (migration 0041).
        parent_version=assessment.version,
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

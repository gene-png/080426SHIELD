"""Tenant authorization helpers.

Routes that operate on a single Service / Artifact / Assessment by id use
these to enforce that the row belongs to the active tenant. Without these
checks a client could read another client's data by guessing the id.

Pattern in a route:

    @router.get("/csf/services/{service_id}/score")
    def score(
        service_id: uuid.UUID,
        client: Annotated[Client, Depends(current_client)],
        db: Annotated[Session, Depends(get_db)],
    ):
        svc = require_service_in_tenant(db, service_id, client.id, kind=ServiceKind.NIST_CSF)
        ...
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.artifact import Artifact
from app.models.attack_assessment import AttackAssessment
from app.models.csf_assessment import CsfAssessment
from app.models.deliverable import Deliverable
from app.models.service import Service, ServiceKind
from app.models.zt_assessment import ZtAssessment


def require_service_in_tenant(
    db: Session,
    service_id: uuid.UUID,
    tenant_client_id: uuid.UUID,
    *,
    kind: ServiceKind | None = None,
) -> Service:
    """Load a Service, verify tenant ownership, optionally verify kind.

    Raises 404 for missing rows AND tenant-mismatch rows (we deliberately
    don't leak existence to other tenants via 403 vs 404).
    """
    svc = db.get(Service, service_id)
    if svc is None or svc.client_id != tenant_client_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found.",
        )
    if kind is not None and svc.kind != kind:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service not found ({kind.value} expected).",
        )
    return svc


def require_artifact_in_tenant(
    db: Session,
    artifact_id: uuid.UUID,
    tenant_client_id: uuid.UUID,
) -> Artifact:
    art = db.get(Artifact, artifact_id)
    if art is None or art.client_id != tenant_client_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found.",
        )
    return art


def require_csf_assessment_in_tenant(
    db: Session, assessment_id: uuid.UUID, tenant_client_id: uuid.UUID
) -> CsfAssessment:
    a = db.get(CsfAssessment, assessment_id)
    if a is None or a.client_id != tenant_client_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found.",
        )
    return a


def require_zt_assessment_in_tenant(
    db: Session, assessment_id: uuid.UUID, tenant_client_id: uuid.UUID
) -> ZtAssessment:
    a = db.get(ZtAssessment, assessment_id)
    if a is None or a.client_id != tenant_client_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found.",
        )
    return a


def require_attack_assessment_in_tenant(
    db: Session, assessment_id: uuid.UUID, tenant_client_id: uuid.UUID
) -> AttackAssessment:
    a = db.get(AttackAssessment, assessment_id)
    if a is None or a.client_id != tenant_client_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found.",
        )
    return a


def require_deliverable_in_tenant(
    db: Session, deliverable_id: uuid.UUID, tenant_client_id: uuid.UUID
) -> Deliverable:
    """Deliverables don't carry client_id directly; verify via parent service."""
    deliv = db.get(Deliverable, deliverable_id)
    if deliv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deliverable not found.",
        )
    svc = db.get(Service, deliv.service_id)
    if svc is None or svc.client_id != tenant_client_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deliverable not found.",
        )
    return deliv

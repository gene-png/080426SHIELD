"""Provision an engagement workspace (Service) + a seeded DRAFT assessment from
a ServiceRequest.

Used at intake submit so a client can immediately begin their self-assessment
for the questionnaire-driven services (NIST CSF, Zero Trust). The seeding mirrors
the admin "create assessment" endpoints so the workspace and the client see the
same deterministic answer grid.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.audit import audit
from app.csf.catalog import SUBCATEGORIES
from app.models.csf_assessment import CsfAnswer, CsfAssessment, CsfAssessmentStatus
from app.models.service import Service, ServiceKind, ServiceStatus
from app.models.service_request import ServiceRequest, ServiceType
from app.models.zt_assessment import (
    ZtAnswer,
    ZtAssessment,
    ZtAssessmentStatus,
    ZtFramework,
)
from app.zt.catalog import capabilities
from app.zt.maturity import ZtFrameworkCode

# Service types that get a client self-assessment questionnaire provisioned.
SELF_ASSESSMENT_TYPES: tuple[ServiceType, ...] = (
    ServiceType.NIST_CSF,
    ServiceType.ZERO_TRUST_CISA,
    ServiceType.ZERO_TRUST_DOD,
)

_SERVICE_TITLES: dict[ServiceType, str] = {
    ServiceType.NIST_CSF: "NIST CSF 2.0 Assessment",
    ServiceType.ZERO_TRUST_CISA: "Zero Trust (CISA ZTMM 2.0)",
    ServiceType.ZERO_TRUST_DOD: "Zero Trust (DoD ZTRA)",
}

_KIND_TO_ZT_FRAMEWORK: dict[ServiceKind, ZtFramework] = {
    ServiceKind.ZERO_TRUST_CISA: ZtFramework.CISA_ZTMM_2_0,
    ServiceKind.ZERO_TRUST_DOD: ZtFramework.DOD_ZTRA,
}

_ZT_FRAMEWORK_TO_CATALOG: dict[ZtFramework, ZtFrameworkCode] = {
    ZtFramework.CISA_ZTMM_2_0: ZtFrameworkCode.CISA_ZTMM_2_0,
    ZtFramework.DOD_ZTRA: ZtFrameworkCode.DOD_ZTRA,
}


def provision_self_assessment_service(
    db: Session,
    sr: ServiceRequest,
    *,
    org_name: str,
    actor_user_id: uuid.UUID,
    title: str | None = None,
) -> Service:
    """Open a Service for `sr` and seed its v1 DRAFT assessment.

    Caller is responsible for the surrounding transaction (this flushes but
    does not commit). For the one-time intake flow the caller also guards
    idempotency (don't double-provision the same client/kind); the
    multi-engagement flow intentionally allows multiple of the same kind, so
    `title` can name each engagement distinctly. Sets
    `sr.fulfilled_service_id` to the new service.
    """
    kind = ServiceKind(sr.service_type.value)
    svc = Service(
        kind=kind,
        status=ServiceStatus.IN_PROGRESS,
        title=(
            title.strip()
            if title and title.strip()
            else f"{org_name} — {_SERVICE_TITLES[sr.service_type]}"
        ),
        client_id=sr.client_id,
        source_request_id=sr.id,
        opened_by=actor_user_id,
    )
    db.add(svc)
    db.flush()

    if sr.service_type == ServiceType.NIST_CSF:
        assessment = CsfAssessment(
            service_id=svc.id,
            client_id=sr.client_id,
            version=1,
            status=CsfAssessmentStatus.DRAFT,
        )
        db.add(assessment)
        db.flush()
        for sc in SUBCATEGORIES:
            db.add(
                CsfAnswer(
                    assessment_id=assessment.id,
                    client_id=sr.client_id,
                    subcategory_code=sc.code,
                )
            )
    else:  # Zero Trust (CISA or DoD)
        framework = _KIND_TO_ZT_FRAMEWORK[kind]
        assessment = ZtAssessment(
            service_id=svc.id,
            client_id=sr.client_id,
            framework=framework,
            version=1,
            status=ZtAssessmentStatus.DRAFT,
        )
        db.add(assessment)
        db.flush()
        for cap in capabilities(_ZT_FRAMEWORK_TO_CATALOG[framework]):
            db.add(
                ZtAnswer(
                    assessment_id=assessment.id,
                    client_id=sr.client_id,
                    capability_code=cap.code,
                )
            )

    sr.fulfilled_service_id = svc.id
    audit(
        db,
        action="service_request.auto_provisioned",
        target_type="service",
        target_id=svc.id,
        actor_user_id=actor_user_id,
        details={"service_type": sr.service_type.value, "request_id": str(sr.id)},
    )
    return svc

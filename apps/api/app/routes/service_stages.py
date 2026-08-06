"""One progress vocabulary for all four services — read-only.

`GET /services/{service_id}/stages` answers "how far along is this?" in the same
six words whatever the service, so the four workspaces can stop each inventing
their own progress language.

Strictly presentation. Nothing here writes, no status is reinterpreted, and no
service's state machine, routes or audit vocabulary change. The derivation and
its version-anchoring live in app.services.stages; this module only finds the
current version row for a service and hands over its status and `created_at`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import current_client, current_user
from app.models.attack_assessment import AttackAssessment
from app.models.capability import CapabilityList
from app.models.client import Client
from app.models.csf_assessment import CsfAssessment
from app.models.service import Service, ServiceKind
from app.models.user import User
from app.models.zt_assessment import ZtAssessment
from app.services.stages import (
    Stage,
    analysis_ran_for_version,
    deliverable_exists_for_version,
    derive_stages,
)

router = APIRouter(prefix="/services", tags=["services"])

# The version-carrying table per service kind. Each has `version`, `status` and
# TimestampMixin's `created_at`, which is all the derivation needs.
_VERSION_MODEL = {
    ServiceKind.TECH_DEBT: CapabilityList,
    ServiceKind.ZERO_TRUST_CISA: ZtAssessment,
    ServiceKind.ZERO_TRUST_DOD: ZtAssessment,
    ServiceKind.NIST_CSF: CsfAssessment,
    ServiceKind.ATTACK_COVERAGE: AttackAssessment,
}

# Statuses that mean the client has finished their self-assessment. Only Zero
# Trust and CSF have this step at all.
_CLIENT_SUBMITTED = frozenset({"submitted", "approved", "released"})


class StageResponse(BaseModel):
    key: str
    state: str


class ServiceStagesResponse(BaseModel):
    service_id: uuid.UUID
    kind: ServiceKind
    #: None when the service has no version row yet — nothing has been started.
    version: int | None
    stages: list[StageResponse]


@router.get(
    "/{service_id}/stages",
    response_model=ServiceStagesResponse,
    summary="Derived six-stage progress for a service",
)
def service_stages(
    service_id: uuid.UUID,
    _user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> ServiceStagesResponse:
    svc = db.get(Service, service_id)
    if svc is None or svc.client_id != client.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found.",
        )

    model = _VERSION_MODEL.get(svc.kind)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This service kind has no staged workflow.",
        )

    # Latest non-discarded version — the same rule the workspaces' own "latest"
    # lookups use, so the bar describes the version on screen.
    row = (
        db.execute(
            select(model)
            .where(model.service_id == service_id, model.status != "discarded")
            .order_by(model.version.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        # Nothing started yet: every stage pending, `prepare` current.
        stages = derive_stages(
            kind=svc.kind,
            status="draft",
            client_input_received=False,
            analyzed=False,
            generated=False,
        )
        return ServiceStagesResponse(
            service_id=service_id,
            kind=svc.kind,
            version=None,
            stages=_out(stages),
        )

    created_at = row.created_at
    return ServiceStagesResponse(
        service_id=service_id,
        kind=svc.kind,
        version=row.version,
        stages=_out(
            derive_stages(
                kind=svc.kind,
                status=str(row.status),
                client_input_received=str(row.status) in _CLIENT_SUBMITTED,
                analyzed=analysis_ran_for_version(
                    db,
                    service_id=service_id,
                    kind=svc.kind,
                    version_created_at=created_at,
                ),
                generated=deliverable_exists_for_version(
                    db,
                    service_id=service_id,
                    version_created_at=created_at,
                ),
            )
        ),
    )


def _out(stages: list[Stage]) -> list[StageResponse]:
    return [StageResponse(key=s.key, state=s.state) for s in stages]

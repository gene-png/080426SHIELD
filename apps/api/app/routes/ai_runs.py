"""Reading Run-AI runs (#645): the poll, and what a workspace needs on load.

Same authorization as every Run-AI POST: an admin, inside the tenant chosen by
`current_client`. A run's `result` carries model-authored text about the
client's posture, so a client-role user is refused, and another tenant's run is
a 404 rather than a 403 so its existence does not leak.

Every read reaps first (`app/ai/runs.py`): a RUNNING run with no job behind it
is ended before it is reported, so a poll never shows a run as in progress
that nothing will finish.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.runs import running_run, to_response
from app.db.session import get_db
from app.dependencies import current_client, require_role
from app.logging import get_logger
from app.models.ai_run import AiRun, AiRunStatus
from app.models.client import Client
from app.models.user import User, UserRole
from app.schemas.ai_runs import AiRunResponse, AiRunSummary
from app.tenant import require_service_in_tenant

_log = get_logger(__name__)

router = APIRouter(prefix="/ai-runs", tags=["ai"])

_admin_required = Depends(require_role(UserRole.ADMIN))


@router.get(
    "/{run_id}",
    response_model=AiRunResponse,
    summary="One Run-AI run: running, completed with its result, or failed (admin)",
)
def get_run(
    run_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> AiRunResponse:
    run = db.get(AiRun, run_id)
    if run is None or run.client_id != client.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    if run.status == AiRunStatus.RUNNING:
        running_run(db, service_id=run.service_id, purpose=run.purpose)  # reaps first
        db.refresh(run)
    _log.info("ai_runs.read", run_id=str(run.id), status=run.status.value)
    return to_response(run)


def _newest(db: Session, service_id: uuid.UUID, *only: AiRunStatus) -> AiRun | None:
    q = select(AiRun).where(AiRun.service_id == service_id)
    if only:
        q = q.where(AiRun.status.in_(only))
    return db.execute(q.order_by(AiRun.started_at.desc())).scalars().first()


@router.get(
    "/services/{service_id}",
    response_model=AiRunSummary,
    summary="The run holding a service's lock, its newest run, and its last completed run (admin)",
)
def service_runs(
    service_id: uuid.UUID,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> AiRunSummary:
    svc = require_service_in_tenant(db, service_id, client.id)
    running = running_run(db, service_id=svc.id)  # reaps first
    latest = _newest(db, svc.id)
    last_completed = _newest(db, svc.id, AiRunStatus.COMPLETED)
    return AiRunSummary(
        running=to_response(running) if running else None,
        latest=to_response(latest) if latest else None,
        last_completed=to_response(last_completed) if last_completed else None,
    )

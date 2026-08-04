"""Redaction preview gate: POST /ai/preview (Sprint 5 T6, audit §4c #3).

Shows an admin EXACTLY what a service's next Run-AI would send to the model —
AFTER redaction — WITHOUT egressing and WITHOUT writing an ``llm_calls`` row.

The payload is built by the SAME per-service ``build_*_ai_request`` function the
real run-ai path uses (see ``app.ai.preview``), so a preview can never diverge
from what actually egresses. This route only runs that payload through the pure
``redact_payload`` and returns the redacted object + removed counts. It never
constructs an LLM provider.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.engine import get_job
from app.ai.preview import AiPreviewPayload
from app.ai.redact import redact_payload
from app.config import get_settings
from app.db.session import get_db
from app.dependencies import current_client, require_role
from app.logging import get_logger
from app.models.client import Client
from app.models.service import Service, ServiceKind
from app.models.user import User, UserRole
from app.routes.attack import build_attack_ai_request
from app.routes.csf import build_csf_ai_request
from app.routes.zt import build_zt_ai_request
from app.schemas.ai import AiPreviewRequest, AiPreviewResponse
from app.security.rate_limit import enforce_ai_rate_limit
from app.tenant import require_service_in_tenant

router = APIRouter(prefix="/ai", tags=["ai"])

_admin_required = Depends(require_role(UserRole.ADMIN))

_log = get_logger(__name__)

# ServiceKind -> the run-ai request builder for that service's Run-AI job.
_BUILDERS = {
    ServiceKind.NIST_CSF: build_csf_ai_request,
    ServiceKind.ZERO_TRUST_CISA: build_zt_ai_request,
    ServiceKind.ZERO_TRUST_DOD: build_zt_ai_request,
    ServiceKind.ATTACK_COVERAGE: build_attack_ai_request,
}


@router.post(
    "/preview",
    response_model=AiPreviewResponse,
    summary="Preview the redacted payload a Run-AI would send — no egress (admin)",
)
def preview_ai_payload(
    body: AiPreviewRequest,
    user: Annotated[User, _admin_required],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
    _rl: Annotated[None, Depends(enforce_ai_rate_limit)],
) -> AiPreviewResponse:
    """Build the service's run-ai payload and return it AFTER redaction.

    Deliberately does NOT run the job: no provider is constructed, no
    ``llm_calls`` row is written, nothing egresses. Reuses the exact payload
    builder run-ai uses so the preview equals what would actually be sent.
    """
    svc: Service = require_service_in_tenant(db, body.service_id, client.id)
    builder = _BUILDERS.get(svc.kind)
    if builder is None:
        # tech_debt's AI is inventory extraction from an uploaded artifact, not a
        # state-based Run-AI — no preview surface. Fail loudly + typed.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "reason": "preview_unsupported",
                "message": "This service has no Run-AI payload to preview.",
            },
        )

    request: object = builder(db, svc, client)
    payload: AiPreviewPayload = request.preview  # type: ignore[attr-defined]

    # Match LLMClient.invoke's default: mode falls back to the configured
    # redaction mode when the run-ai caller passes none (all of them do).
    mode = get_settings().shield_redaction_mode
    cleaned, removed_counts = redact_payload(
        payload.inputs,
        mode=mode,
        client_org_name=payload.client_org_name,
        name_hints=payload.name_hints,
    )

    purpose = get_job(payload.job_name).call_purpose
    _log.info(
        "ai_preview_built",
        service_id=str(svc.id),
        kind=svc.kind.value,
        purpose=purpose,
        redaction_mode=mode,
        removed=removed_counts,
    )
    return AiPreviewResponse(
        purpose=purpose,
        redaction_mode=mode,
        payload=cleaned,
        removed_counts=removed_counts,
    )

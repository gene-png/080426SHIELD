"""Shared deliverable release action (Sprint 5 T1, D-025).

One helper behind the four per-service release routes (csf/zt/attack/tech_debt),
which are shape-identical apart from their service kind and audit-action prefix.
Master Spec §12: a client sees nothing until a consultant explicitly releases a
FINALIZED deliverable. This is a new admin-only action, not a revival of the
removed D-005/D-006 reviewer gate (D-023).
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.email.sender import send_release_notification
from app.logging import get_logger
from app.models._common import utcnow
from app.models.deliverable import Deliverable
from app.models.service import Service, ServiceKind
from app.models.user import User, UserRole
from app.tenant import require_deliverable_in_tenant

_log = get_logger(__name__)

# Human-readable service names for the client-facing release notification.
_SERVICE_LABELS: dict[ServiceKind, str] = {
    ServiceKind.TECH_DEBT: "Technical Debt Review",
    ServiceKind.ZERO_TRUST_CISA: "Zero Trust (CISA ZTMM)",
    ServiceKind.ZERO_TRUST_DOD: "Zero Trust (DoD ZTRA)",
    ServiceKind.NIST_CSF: "NIST CSF 2.0",
    ServiceKind.ATTACK_COVERAGE: "MITRE ATT&CK Coverage",
}


def release_deliverable(
    db: Session,
    *,
    deliverable_id: uuid.UUID,
    tenant_client_id: uuid.UUID,
    user: User,
    kinds: tuple[ServiceKind, ...],
    action: str,
) -> Deliverable:
    """Release a finalized deliverable to the client.

    Tenant-enforced (404 on mismatch, never 403), kind-checked so a service's
    route only releases its own deliverables (`kinds` is the set the calling
    router serves — one for csf/attack/tech_debt, two for zt), and idempotent:
    re-releasing an already-released deliverable is a logged no-op, not an error.

    Raises:
        HTTPException 404: unknown / cross-tenant / wrong-kind deliverable.
        HTTPException 409: deliverable was never finalized (typed `not_finalized`).
    """
    deliv = require_deliverable_in_tenant(db, deliverable_id, tenant_client_id)
    svc = db.get(Service, deliv.service_id)
    if svc is None or svc.kind not in kinds:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deliverable not found.",
        )

    if deliv.finalized_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "not_finalized",
                "message": "Finalize the deliverable before releasing it to the client.",
            },
        )

    if deliv.released_at is not None:
        # Idempotent: already released. Loud no-op so a re-release is auditable
        # in the logs without a second audit row or a lie that it "changed".
        _log.info(
            "deliverable.release noop (already released)",
            deliverable_id=str(deliv.id),
            action=action,
            released_at=deliv.released_at.isoformat(),
            actor_user_id=str(user.id),
        )
        return deliv

    deliv.released_at = utcnow()
    deliv.released_by = user.id
    audit(
        db,
        action=action,
        target_type="deliverable",
        target_id=deliv.id,
        actor_user_id=user.id,
        details={
            "service_id": str(svc.id),
            "service_kind": svc.kind.value,
            "version": deliv.version,
        },
    )
    _log.info(
        "deliverable.released",
        deliverable_id=str(deliv.id),
        action=action,
        service_kind=svc.kind.value,
        actor_user_id=str(user.id),
    )
    db.commit()
    db.refresh(deliv)

    # Best-effort client notification (D-030). The release is already committed
    # and is the source of truth; a notification failure must never roll it back.
    _notify_release(db, svc=svc, deliv=deliv, tenant_client_id=tenant_client_id)
    return deliv


def _notify_release(
    db: Session,
    *,
    svc: Service,
    deliv: Deliverable,
    tenant_client_id: uuid.UUID,
) -> None:
    """Email the tenant's active client-role users that a deliverable released.

    Gated by ``shield_email_delivery_enabled`` (loud skip log when off, so a
    deployment never silently believes it notified). Sends are best-effort: a
    per-recipient send failure is logged LOUDLY and the release stands (D-030 —
    the release is the source of truth, the email is notify-only).
    """
    if not get_settings().shield_email_delivery_enabled:
        _log.info(
            "deliverable.release notify skipped (delivery disabled)",
            deliverable_id=str(deliv.id),
        )
        return

    recipients = list(
        db.execute(
            select(User.email).where(
                User.client_id == tenant_client_id,
                User.role == UserRole.CLIENT,
                User.is_active.is_(True),
            )
        ).scalars()
    )
    service_label = _SERVICE_LABELS.get(svc.kind, svc.kind.value)
    sent = 0
    failed = 0
    for email in recipients:
        try:
            send_release_notification(
                to=email,
                service_label=service_label,
                title=deliv.title,
                version=deliv.version,
            )
            sent += 1
        except Exception as exc:  # noqa: BLE001 - best-effort notify (D-030): loud, no rollback
            failed += 1
            _log.error(
                "deliverable.release notify failed",
                deliverable_id=str(deliv.id),
                recipient=email,
                error=str(exc),
                exc_info=True,
            )
    _log.info(
        "deliverable.release notified",
        deliverable_id=str(deliv.id),
        recipients=len(recipients),
        sent=sent,
        failed=failed,
    )

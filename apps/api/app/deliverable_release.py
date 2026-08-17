"""Shared deliverable release action (Sprint 5 T1, D-025).

One helper behind the four per-service release routes (csf/zt/attack/tech_debt),
which are shape-identical apart from their service kind and audit-action prefix.
Master Spec §12: a client sees nothing until a consultant explicitly releases a
FINALIZED deliverable. This is a new admin-only action, not a revival of the
removed D-005/D-006 reviewer gate (D-023).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.email.sender import send_release_notification
from app.logging import get_logger
from app.models._common import utcnow
from app.models.attack_assessment import AttackAssessment, AttackAssessmentStatus
from app.models.capability import CapabilityList, CapabilityListStatus
from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus
from app.models.deliverable import Deliverable
from app.models.service import Service, ServiceKind
from app.models.user import User, UserRole
from app.models.zt_assessment import ZtAssessment, ZtAssessmentStatus
from app.tenant import require_deliverable_in_tenant

_log = get_logger(__name__)


@dataclass(frozen=True)
class _Parent:
    """The record a release also has to flip (W4)."""

    model: type
    status_enum: type


# Which parent record each service kind releases. There was no such map before
# W4 — `release_deliverable` knew only a `kinds` tuple and an audit-action
# string, which is why nothing outside the seed script ever assigned RELEASED.
_PARENTS: dict[ServiceKind, _Parent] = {
    ServiceKind.TECH_DEBT: _Parent(CapabilityList, CapabilityListStatus),
    ServiceKind.NIST_CSF: _Parent(CsfAssessment, CsfAssessmentStatus),
    ServiceKind.ZERO_TRUST_CISA: _Parent(ZtAssessment, ZtAssessmentStatus),
    ServiceKind.ZERO_TRUST_DOD: _Parent(ZtAssessment, ZtAssessmentStatus),
    ServiceKind.ATTACK_COVERAGE: _Parent(AttackAssessment, AttackAssessmentStatus),
}


def _release_parent(db: Session, *, deliv: Deliverable, svc: Service, action: str) -> None:
    """Flip the parent this deliverable was built from to RELEASED (W4).

    No API route assigned RELEASED before this; the only writer in the repo was
    `seed_demo.py`. The consequence a client could see: `services/stages.py`
    derives `released` from the PARENT status rather than from
    `deliverables.released_at`, so a service released through the product showed
    `release` as its current incomplete stage while the report was already
    delivered. It also left Tech Debt's `_editable_list_or_404` lock dead code.

    The row is identified by the version stamped at finalize (migration 0041),
    NOT by "latest APPROVED". Those differ after
    `approve v1 -> finalize -> cut v2 -> approve v2 -> release`, where the latest
    rule would flip a version the released report was never built from.

    Two refusals, both loud and neither fatal — the release itself is committed
    by the caller and is the source of truth (the D-030 rule):

    * `parent_version` is NULL — finalized before 0041. Guessing is the thing the
      column exists to prevent, so it does not guess.
    * the parent is not APPROVED — flipping a DRAFT would skip APPROVED entirely
      and lock work in progress; anything else is already terminal.
    """
    parent = _PARENTS.get(svc.kind)
    if parent is None:  # pragma: no cover - every kind is mapped above
        raise RuntimeError(f"No parent record mapped for service kind {svc.kind!r}")

    if deliv.parent_version is None:
        _log.warning(
            "deliverable.release_parent_unknown",
            deliverable_id=str(deliv.id),
            action=action,
            service_kind=svc.kind.value,
            detail="finalized before migration 0041; parent status left unchanged",
        )
        return

    row = (
        db.execute(
            select(parent.model).where(
                parent.model.service_id == svc.id,
                parent.model.version == deliv.parent_version,
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        _log.warning(
            "deliverable.release_parent_missing",
            deliverable_id=str(deliv.id),
            action=action,
            service_kind=svc.kind.value,
            parent_version=deliv.parent_version,
        )
        return
    if row.status == parent.status_enum.RELEASED:
        # Already there, and this is a NORMAL path: finalize accepts a RELEASED
        # parent in all four services, so re-finalizing after a release and then
        # releasing v2 lands here with nothing to do. Logged at INFO, not as a
        # warning — otherwise the healthy case is indistinguishable from the two
        # broken ones below, and the warning that exists to surface them becomes
        # noise nobody reads.
        _log.info(
            "deliverable.release_parent_already_released",
            deliverable_id=str(deliv.id),
            action=action,
            service_kind=svc.kind.value,
            parent_version=deliv.parent_version,
        )
        return
    if row.status != parent.status_enum.APPROVED:
        _log.warning(
            "deliverable.release_parent_not_approved",
            deliverable_id=str(deliv.id),
            action=action,
            service_kind=svc.kind.value,
            parent_version=deliv.parent_version,
            parent_status=row.status.value,
        )
        return

    row.status = parent.status_enum.RELEASED
    _log.info(
        "deliverable.release_parent_released",
        deliverable_id=str(deliv.id),
        action=action,
        service_kind=svc.kind.value,
        parent_version=deliv.parent_version,
    )


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
        # ...but STILL try the parent flip, because this is the repair path.
        # Anything released before W4, or released while `parent_version` was
        # unknown, has a parent stuck on APPROVED and a progress bar telling the
        # consultant a delivered report still needs releasing. Without this, the
        # only fix was direct SQL: the release is idempotent, so re-releasing
        # changed nothing, forever. Re-releasing now repairs it.
        _release_parent(db, deliv=deliv, svc=svc, action=action)
        if db.is_modified(deliv) or db.dirty:
            db.commit()
        return deliv

    deliv.released_at = utcnow()
    deliv.released_by = user.id
    # In the SAME transaction as `released_at`, and after the idempotent
    # early-return above so a re-release cannot re-flip. The deliverable being
    # released and its parent reading RELEASED are one fact; committing one
    # without the other is what produced the stage bar claiming a released
    # service still had releasing left to do.
    _release_parent(db, deliv=deliv, svc=svc, action=action)
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

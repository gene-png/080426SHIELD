"""`spine.audit()` - the only blessed way to write an audit_entries row.

Master Spec §11 + AI Prompt §4.5: every state-changing route logs an
audit entry. Calling this from a request handler automatically pulls the
correlation ID from the request-scoped context, so callers don't have to
plumb it manually.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.logging import correlation_id_var, get_logger
from app.models.audit_entry import AuditEntry

_log = get_logger(__name__)


def audit(
    db: Session,
    *,
    action: str,
    target_type: str,
    target_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEntry:
    """Append one audit_entries row, in the caller's session.

    The row is added to the session; the caller is responsible for the
    surrounding commit (so the audit row commits or rolls back atomically
    with the business change it describes).

    Args:
        db: SQLAlchemy session for the current request.
        action: verb describing what happened, e.g. "user.created",
            "deliverable.released". Stable identifier; do not include
            user-supplied strings.
        target_type: ORM table name or logical resource type, e.g. "user".
        target_id: UUID of the affected row, when known.
        actor_user_id: UUID of the acting user, or None for system actions.
        details: small JSON-serializable payload of additional context.
            DO NOT include PII or the redacted/un-redacted content of any
            LLM call here. Hashes are fine; raw secrets are not.

    Returns:
        The added AuditEntry (still pending flush).
    """
    entry = AuditEntry(
        action=action,
        target_type=target_type,
        target_id=target_id,
        actor_user_id=actor_user_id,
        details=details,
        correlation_id=correlation_id_var.get(),
    )
    db.add(entry)
    _log.info(
        "audit",
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id else None,
        actor_user_id=str(actor_user_id) if actor_user_id else None,
    )
    return entry

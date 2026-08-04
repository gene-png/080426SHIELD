"""`notify()` / `notify_role()` - blessed write surface for the notifications
table.

Master Spec §11 + §15 Phase 2 ("admin notification fires on intake submit").
AI Prompt §6.12 ("NEVER point the notification bell at the home page") -
callers should pass a real `link` that resolves to a working page; this
helper does not enforce it (the route-level test does).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User, UserRole


def notify(
    db: Session,
    *,
    user_id: uuid.UUID,
    event_type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
) -> Notification:
    """Append a notification row for a specific user."""
    row = Notification(
        user_id=user_id,
        event_type=event_type,
        title=title,
        body=body,
        link=link,
    )
    db.add(row)
    return row


def notify_role(
    db: Session,
    *,
    role: UserRole,
    event_type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
) -> list[Notification]:
    """Append a notification row for every user with the given role.

    Used by spec-§15 Phase 2's "admin notification fires on intake submit":
    we fan-out to every admin so any consultant on the engagement sees it.
    """
    targets = db.execute(select(User.id).where(User.role == role)).scalars().all()
    return [
        notify(
            db,
            user_id=user_id,
            event_type=event_type,
            title=title,
            body=body,
            link=link,
        )
        for user_id in targets
    ]

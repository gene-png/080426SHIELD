"""Notification routes.

Master Spec §11 + AI Prompt §6.12 ("NEVER point the notification bell at
the home page"). The link must resolve to a working page; for v1 the only
notification type is `intake.submitted`, which links the admin to
/admin/queue.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import current_user
from app.models._common import utcnow
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationListResponse, NotificationResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="Current user's notifications, newest first",
)
def list_notifications(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> NotificationListResponse:
    rows = (
        db.execute(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    unread = db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    ).scalar_one()
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(r, from_attributes=True) for r in rows],
        unread_count=unread,
    )


@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark a single notification read",
)
def mark_read(
    notification_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> NotificationResponse:
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )
    if row.read_at is None:
        row.read_at = utcnow()
    db.commit()
    db.refresh(row)
    return NotificationResponse.model_validate(row, from_attributes=True)


@router.post(
    "/read-all",
    response_model=NotificationListResponse,
    summary="Mark every notification read for the current user",
)
def mark_all_read(
    user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> NotificationListResponse:
    now = utcnow()
    rows = (
        db.execute(
            select(Notification).where(
                Notification.user_id == user.id, Notification.read_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.read_at = now
    db.commit()
    return list_notifications(user, db)

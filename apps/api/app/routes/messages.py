"""Per-service message thread (Work Order C7).

Both an admin (cross-tenant via X-Client-Id) and the service's own client user
can read and post. Tenant-scoped: the service must belong to the active client.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.db.session import get_db
from app.dependencies import current_client, current_user
from app.models._common import utcnow
from app.models.client import Client
from app.models.message import Message
from app.models.service import Service
from app.models.user import User
from app.schemas.message import (
    InboxResponse,
    InboxThread,
    MessageCreateRequest,
    MessageListResponse,
    MessageRow,
)
from app.tenant import require_service_in_tenant

router = APIRouter(tags=["messages"])


def _serialize(db: Session, m: Message) -> MessageRow:
    role: str | None = None
    if m.author_user_id is not None:
        author = db.get(User, m.author_user_id)
        role = author.role.value if author is not None else None
    return MessageRow(
        id=m.id,
        service_id=m.service_id,
        author_user_id=m.author_user_id,
        author_role=role,
        body=m.body,
        created_at=m.created_at,
        read_at=m.read_at,
    )


@router.get(
    "/services/{service_id}/messages",
    response_model=MessageListResponse,
    summary="List the message thread for a service",
)
def list_messages(
    service_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageListResponse:
    require_service_in_tenant(db, service_id, client.id)
    rows = (
        db.execute(
            select(Message)
            .where(Message.service_id == service_id)
            .order_by(Message.created_at.asc())
        )
        .scalars()
        .all()
    )
    # Mark the counterparty's unread messages as read now that this user saw them.
    now = utcnow()
    for m in rows:
        if m.read_at is None and m.author_user_id != user.id:
            m.read_at = now
    db.commit()
    return MessageListResponse(messages=[_serialize(db, m) for m in rows])


@router.post(
    "/services/{service_id}/messages",
    response_model=MessageRow,
    status_code=status.HTTP_201_CREATED,
    summary="Post a message to a service thread",
)
def post_message(
    service_id: uuid.UUID,
    body: MessageCreateRequest,
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageRow:
    require_service_in_tenant(db, service_id, client.id)
    text = body.body.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message body cannot be empty.",
        )
    msg = Message(
        client_id=client.id,
        service_id=service_id,
        author_user_id=user.id,
        body=text,
    )
    db.add(msg)
    db.flush()
    audit(
        db,
        action="message.posted",
        target_type="service",
        target_id=service_id,
        actor_user_id=user.id,
        details={"message_id": str(msg.id)},
    )
    db.commit()
    db.refresh(msg)
    return _serialize(db, msg)


@router.get(
    "/messages/inbox",
    response_model=InboxResponse,
    summary="Per-service thread summaries for the active client",
)
def inbox(
    user: Annotated[User, Depends(current_user)],
    client: Annotated[Client, Depends(current_client)],
    db: Annotated[Session, Depends(get_db)],
) -> InboxResponse:
    """One row per service with a thread, newest activity first. Unread counts
    the counterparty's messages this user hasn't opened yet."""
    rows = (
        db.execute(
            select(Message).where(Message.client_id == client.id).order_by(Message.created_at.asc())
        )
        .scalars()
        .all()
    )
    # Aggregate per service in code (small per-client volume).
    by_service: dict[uuid.UUID, list[Message]] = {}
    for m in rows:
        by_service.setdefault(m.service_id, []).append(m)

    threads: list[InboxThread] = []
    unread_total = 0
    for service_id, msgs in by_service.items():
        svc = db.get(Service, service_id)
        if svc is None or svc.client_id != client.id:
            continue
        unread = sum(1 for m in msgs if m.read_at is None and m.author_user_id != user.id)
        unread_total += unread
        last = msgs[-1]
        threads.append(
            InboxThread(
                service_id=service_id,
                service_title=svc.title,
                service_kind=svc.kind.value,
                total=len(msgs),
                unread=unread,
                last_preview=(last.body[:140] if last.body else None),
                last_at=last.created_at,
            )
        )
    threads.sort(key=lambda t: (t.last_at is None, t.last_at), reverse=True)
    return InboxResponse(threads=threads, unread_total=unread_total)

"""Refuse a session to a user of an archived client (#727, D-104).

Gene's decision, 2026-09-26 (#736): a user whose client is archived
(`Client.archived_at IS NOT NULL`) cannot start a session by any path, and the
refusal is typed the way an inactive user's is. #726 (D-103) ENDS the sessions
an archive finds; this refuses the next one.

Callers: password login, the MFA verify step, the OIDC exchange, refresh,
registration (a registrant whose domain maps to the archived client would join
it), and `current_client`, which covers an access token already issued. Every
session-issuing path is a caller of `routes/auth._issue_pair`; a new caller of
`_issue_pair` that does not call this reopens #727.

The message names no remedy (D-076): there is no in-product control that
un-archives a client, and none a client user can reach.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.user import User

CLIENT_ARCHIVED = "client_archived"
_MESSAGE = "Your organization's SHIELD account has been archived, so it is no longer available."


def client_archived_error(status_code: int = status.HTTP_403_FORBIDDEN) -> HTTPException:
    """The typed refusal (D-016). 403 everywhere but registration, which answers
    409 like the other refusals about where an email's domain leads."""
    return HTTPException(
        status_code=status_code,
        detail={"reason": CLIENT_ARCHIVED, "message": _MESSAGE},
    )


def is_archived(client: Client | None) -> bool:
    return client is not None and client.archived_at is not None


def user_client_is_archived(db: Session, user: User) -> bool:
    """True when `user` belongs to an archived client.

    Keyed on `client_id`, not on role, matching #726's session ending: every
    user whose `client_id` is the archived client. A Kentro admin has no client
    and is never refused here. A `client_id` naming no row is left to
    `current_client`, which already refuses it.
    """
    if user.client_id is None:
        return False
    return is_archived(db.get(Client, user.client_id))

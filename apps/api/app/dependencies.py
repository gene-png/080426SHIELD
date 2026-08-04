"""FastAPI dependencies: current user + current client (tenant) resolution.

`current_user` reads the `Authorization: Bearer <token>` header, verifies the
access token, and loads the User row. Routes that don't need the user but
need the role take `require_role` instead (Phase 1 stage 7).

`current_client` resolves the active tenant for the request:
  - Client-role user: pinned to user.client_id (request can't escape it).
  - Platform admin (User.client_id IS NULL): must send X-Client-Id header
    naming an existing client. Cross-tenant admin routes that operate on
    all clients (e.g. GET /admin/clients) should not take this dependency.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.client import Client
from app.models.user import User, UserRole
from app.security.jwt import TokenError, verify_token


def _bearer_token_from(request: Request) -> str:
    auth = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth.split(" ", 1)[1].strip()


def current_user(
    request: Request,
    db: Session = Depends(get_db),  # noqa: B008 - FastAPI dependency-injection idiom
) -> User:
    token = _bearer_token_from(request)
    try:
        payload = verify_token(token, expected_type="access")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.get(User, payload.sub)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is no longer active.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(*allowed: UserRoleT) -> Callable[[User], User]:
    """Build a FastAPI dependency that requires one of the listed roles.

    Usage:
        @router.get("/admin/queue")
        def queue(user: Annotated[User, Depends(require_role(UserRole.ADMIN))]):
            ...

    Returns 403 (not 401) when the caller is authenticated but lacks the
    required role - matches RFC 7231 semantics and helps client code
    distinguish "log in" (401) from "you're logged in but not allowed" (403).
    """

    allowed_set = frozenset(allowed)

    def _guard(user: User = Depends(current_user)) -> User:  # noqa: B008 - FastAPI DI idiom
        if user.role not in allowed_set:
            roles = ", ".join(sorted(r.value for r in allowed_set))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires role: {roles}.",
            )
        return user

    return _guard


def current_client(
    request: Request,
    user: User = Depends(current_user),  # noqa: B008 - FastAPI DI idiom
    db: Session = Depends(get_db),  # noqa: B008 - FastAPI DI idiom
) -> Client:
    """Resolve the active tenant for this request.

    Client-role users are pinned to their own client_id. Platform-level
    users (platform admin with client_id IS NULL) must send X-Client-Id
    to choose which client they're operating on. The header value must
    reference an existing client.
    """
    if user.role == UserRole.CLIENT:
        if user.client_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Client-role user is not bound to a client.",
            )
        client = db.get(Client, user.client_id)
        if client is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Your client account is no longer available.",
            )
        return client

    # Platform admin: client_id is typically NULL; they pick the
    # active tenant via X-Client-Id. If user.client_id is set (legacy data),
    # the header still wins so a platform admin can switch contexts.
    header_val = request.headers.get("X-Client-Id")
    if not header_val:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Client-Id header is required for this role.",
        )
    try:
        client_uuid = uuid.UUID(header_val)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Client-Id must be a UUID.",
        ) from exc
    client = db.get(Client, client_uuid)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No client with that id.",
        )
    return client


# Type aliases (kept at module bottom so the require_role docstring above can
# reference `UserRole` without forcing a top-level import that ruff TCH-pings).
from collections.abc import Callable  # noqa: E402

from app.models.user import UserRole as UserRoleT  # noqa: E402  pylint: disable=unused-import

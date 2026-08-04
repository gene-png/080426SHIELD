"""Correlation-ID middleware.

AI Prompt §4.4: every request gets a correlation ID; every log row uses it;
the user-facing 500 page shows the correlation ID and nothing else.

Reads the inbound `X-Request-ID` header if present (server is welcome to
trust the load-balancer's ID), otherwise generates a UUID4. Always echoes
the ID back in the response `X-Request-ID` header.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging import correlation_id_var

HEADER_NAME = "X-Request-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        inbound = request.headers.get(HEADER_NAME)
        cid = inbound if inbound and _looks_like_id(inbound) else str(uuid.uuid4())
        token = correlation_id_var.set(cid)
        try:
            request.state.correlation_id = cid
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        response.headers[HEADER_NAME] = cid
        return response


def _looks_like_id(value: str) -> bool:
    return 0 < len(value) <= 128 and all(c.isascii() and (c.isalnum() or c in "-_") for c in value)

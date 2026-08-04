"""Global exception handler.

AI Prompt §4.4 + Master Spec §6.3: NEVER expose a stack trace to a client.
The user-facing 500 response carries only the correlation ID. Internal
diagnostics go to the structured log under the matching correlation ID so an
operator can join them.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.logging import get_logger

logger = get_logger(__name__)


def _correlation_id_from(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unknown")


async def _handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    # A route may raise HTTPException with either a plain string detail (the
    # common case) or a typed detail dict {"reason": <machine code>, "message":
    # <human copy>}. The typed form lets the web layer map a specific error to
    # the right field/copy deterministically instead of string-sniffing.
    error: dict[str, object] = {
        "code": exc.status_code,
        "correlation_id": _correlation_id_from(request),
    }
    detail = exc.detail
    if isinstance(detail, dict):
        error["message"] = detail.get("message", "")
        reason = detail.get("reason")
        if reason is not None:
            error["reason"] = reason
    else:
        error["message"] = detail
    # Preserve response headers the route attached to the exception (e.g. a
    # rate-limit 429's Retry-After, or a 401's WWW-Authenticate) — without this
    # they were being silently dropped by the custom envelope.
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error},
        headers=exc.headers or None,
    )


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": 422,
                "message": "Request validation failed.",
                "details": exc.errors(),
                "correlation_id": _correlation_id_from(request),
            }
        },
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    cid = _correlation_id_from(request)
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        correlation_id=cid,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": 500,
                "message": "An internal error occurred. Please contact support.",
                "correlation_id": cid,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected)

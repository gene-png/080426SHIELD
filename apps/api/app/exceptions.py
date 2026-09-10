"""Global exception handler.

AI Prompt §4.4 + Master Spec §6.3: NEVER expose a stack trace to a client.
The user-facing 500 response carries only the correlation ID. Internal
diagnostics go to the structured log under the matching correlation ID so an
operator can join them.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
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
        # Carry any further typed fields the route attached. Without this the
        # envelope silently dropped everything except reason/message — e.g.
        # `charged_likely` on an AI failure, which the UI needs in order to tell
        # the admin whether a retry may cost money a second time.
        for key, value in detail.items():
            if key not in {"message", "reason"} and key not in error:
                error[key] = value
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


def _jsonable_validation_errors(exc: RequestValidationError) -> list[dict[str, object]]:
    """Pydantic hands us live Python objects. `JSONResponse` cannot render them.

    Two ways an error entry arrives unserialisable, and they are NOT the same
    surface -- an earlier version of this function treated only the first and
    asserted in its own docstring that the second could not happen:

    **`ctx["error"]` holds the raised exception itself.** Raising `ValueError`
    is how Pydantic v2 wants a custom validator to reject a value, so the entry
    carries the live instance rather than its text.

    **`input` holds whatever was submitted, which is not always JSON.** This
    handler is registered globally, so it also serves routes taking
    `File(...)` / `Form(...)` -- `upload_artifact` is one -- where a failing
    field's `input` is an `UploadFile`, and routes posted with a non-JSON
    content type, where it is raw `bytes`. Both measured unserialisable
    2026-09-10.

    Either way `json.dumps` raises `TypeError` INSIDE the 422 handler, the
    unexpected-exception handler catches it, and the caller gets a **500** with
    a correlation id -- from the one handler whose whole job is to say what was
    wrong. Core principle 2 failing in the code written to uphold it.

    Latent until 2026-09-10 for the `ctx` half: every validator in
    `app/schemas/` normalised rather than raised, so nothing had ever produced
    a `ctx.error`. `_numeric.IntNotBool` and the two self-assessment patch
    schemas are the first that do. The `input` half is older and still live.

    ## Why `jsonable_encoder` rather than a local coercion

    It is what FastAPI's own default validation handler uses, and `CLAUDE.md`
    is explicit that agreeing with another implementation is a claim to enforce
    by CALLING it, never by reimplementing it. A hand-rolled version was
    written first and was worse in a way that proves the point: it stringified
    every value in `ctx`, so an ordinary range refusal's `{"le": 4}` went out
    as `{"le": "4"}` -- a wire-format change for every client, to fix a case
    that only ever involved one key. `jsonable_encoder` leaves it an int.
    Measured 2026-09-10 across all three inputs: a raised `ValueError`, an
    `UploadFile`, and raw `bytes`.

    Found by an HTTP-level test. Every schema-level assertion passed, because
    Pydantic is perfectly happy to raise -- the defect lives entirely in the
    serialisation of the response.
    """
    return jsonable_encoder(exc.errors())


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": 422,
                "message": "Request validation failed.",
                "details": _jsonable_validation_errors(exc),
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

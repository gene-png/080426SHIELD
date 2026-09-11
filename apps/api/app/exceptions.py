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


#: Namespace for a reason synthesised from Pydantic's own error `type` (#285).
#:
#: The prefix is load-bearing rather than decorative. Hand-written D-016
#: reasons are chosen strings -- `target_stage_out_of_range`,
#: `capability_list_discarded` -- and Pydantic's `type` vocabulary is not ours
#: to control: a future version may add a type that collides with one of them,
#: and a client mapping `reason` to copy would then render a schema failure as
#: a domain refusal. The prefix makes collision impossible by construction
#: instead of by nobody having picked the same word yet.
SCHEMA_REASON_PREFIX = "schema_"

#: The reason when the errors do NOT agree on one type.
SCHEMA_REASON_MIXED = "schema_multiple"


def schema_reasons(details: list[dict[str, object]]) -> list[str]:
    """Distinct `schema_<type>` codes, in first-seen order.

    Order is preserved rather than sorted so the first entry corresponds to the
    first error Pydantic reported, which is the one a form focuses.

    An entry with no usable `type` yields `schema_unknown` rather than being
    skipped. Skipping it would make the list SHORTER than the details it
    summarises, so a client checking "did every error get a code" would be told
    yes over an error that got none -- the silent-discard shape, in the function
    written to end silent discards.
    """
    out: list[str] = []
    for entry in details:
        raw = entry.get("type")
        code = SCHEMA_REASON_PREFIX + (raw if isinstance(raw, str) and raw else "unknown")
        if code not in out:
            out.append(code)
    return out


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """A schema-level refusal carries a typed reason too (#285).

    Core principle 2 says user-facing API errors are typed and "never raw
    validation dumps", and every hand-written refusal in this API follows the
    D-016 shape. A refusal DERIVED from a schema -- `extra="forbid"` plus a
    validator reading `model_fields`, which is what makes it impossible for a
    newly-added field to start being silently dropped -- arrived as Pydantic's
    own list instead, so the client had to sniff strings to tell one cause from
    another.

    The issue offered two repairs and this is the wider one: synthesising the
    reason HERE improves every schema-level 422 in the API rather than the two
    that prompted it, and it keeps the derived refusal set. The alternative --
    moving the refusal into the handler as a typed `HTTPException` -- would have
    reintroduced the enumeration the schema exists to avoid, and that list goes
    stale exactly the way the original defect did.

    **Additive, deliberately.** `code`, `message` and `details` are unchanged
    and in place, so nothing that reads this envelope today breaks. A consumer
    that wants the typed reason opts in.

    `reason` is the single code when every error agrees, and `schema_multiple`
    when they do not; `reasons` always carries the full distinct set. A single
    code for a mixed failure would have to pick one cause and discard the rest,
    which is how a client comes to render "unknown field" over a request that
    also had a value out of range.
    """
    details = _jsonable_validation_errors(exc)
    reasons = schema_reasons(details)
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": 422,
                "message": "Request validation failed.",
                # Absent rather than null when there is nothing to report. An
                # empty error list should not be reachable -- Pydantic does not
                # raise without one -- and inventing `schema_unknown` for it
                # would put a code on a state nobody has seen.
                **(
                    {"reason": reasons[0] if len(reasons) == 1 else SCHEMA_REASON_MIXED}
                    if reasons
                    else {}
                ),
                **({"reasons": reasons} if reasons else {}),
                "details": details,
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

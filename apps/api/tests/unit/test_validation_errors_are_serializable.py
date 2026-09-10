"""A validator that raises must produce a 422, not a 500 from the 422 handler.

Pydantic v2's way to reject a value in a custom validator is to raise
`ValueError`. The resulting error entry carries the **live exception object**
in `ctx["error"]`, and `JSONResponse` calls `json.dumps` on it:

    TypeError: Object of type ValueError is not JSON serializable

raised INSIDE `_handle_validation_error`. The client gets a 500 with a
correlation id, and the typed refusal the validator wrote is destroyed on the
way out — the exact opposite of core principle 2, produced by the handler whose
job is to state the error.

## Latent for the life of the codebase, reachable as of 2026-09-10

Every validator in `app/schemas/` normalised rather than raised, so nothing had
ever produced a `ctx.error`. `_numeric.IntNotBool` and the two self-assessment
patch schemas are the first that do.

Worth recording HOW it was found, because it is the argument for the test that
found it: every schema-level assertion passed. Pydantic is perfectly happy to
raise the error — the defect lives entirely in the serialisation of the
response, so only a test that goes over HTTP can see it. A schema-shape test
suite of any size would have shipped this.

## Why the input comes from a real schema

Hand-building a `ctx` dict containing an exception would make this test agree
with the fix by construction — #72's shape. The error here is produced by
actually validating a real request schema with a real bad value, so the entry's
structure is Pydantic's rather than the author's.

## Why these go through the HANDLER and not the helper

An earlier version of this file called `_jsonable_validation_errors` directly.
Reverting the handler's call site — putting `exc.errors()` back — left it
**green**, because the helper still existed and still worked. It pinned the
unit and not the wiring, which is the same gap that let the schema-level #195
tests stay green while the route was pointed back at the wide admin schema.
Caught by red-on-revert, not by review. Assert on the RESPONSE.
"""

from __future__ import annotations

import json
import types

import pytest
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.exceptions import _handle_validation_error
from app.schemas.zt import ZtAnswerPatch, ZtSelfAssessmentAnswerPatch


def _real_validation_error(model: type, payload: dict) -> RequestValidationError:
    """A RequestValidationError built from a genuine Pydantic failure."""
    try:
        model(**payload)
    except ValidationError as exc:
        return RequestValidationError(exc.errors())
    raise AssertionError(f"{model.__name__} accepted {payload!r}; it must not")


async def _render(exc: RequestValidationError) -> dict:
    """What the client actually receives, via the registered handler."""
    request = types.SimpleNamespace(state=types.SimpleNamespace())
    response = await _handle_validation_error(request, exc)  # type: ignore[arg-type]
    assert response.status_code == 422
    return json.loads(response.body)


@pytest.mark.unit
@pytest.mark.parametrize(
    "model, payload, expected_fragment",
    [
        # A BeforeValidator raising (#189).
        (ZtAnswerPatch, {"maturity_stage": True}, "boolean"),
        # A model_validator raising (#195).
        (ZtSelfAssessmentAnswerPatch, {"target_stage": 3}, "target_stage"),
    ],
)
async def test_a_validator_raising_still_serializes(
    model: type, payload: dict, expected_fragment: str
) -> None:
    """The response body must render, and must still say what was wrong."""
    exc = _real_validation_error(model, payload)

    # The unfixed form. Asserted so this test documents the defect rather than
    # merely avoiding it -- if Pydantic ever stops putting the exception in
    # `ctx`, this fails and the handler can be simplified.
    with pytest.raises(TypeError):
        json.dumps(exc.errors())

    body = await _render(exc)
    rendered = json.dumps(body)
    assert expected_fragment in rendered, (
        f"the 422 body no longer explains the refusal. A serialisable body "
        f"that has lost the reason is not a fix. Rendered: {rendered!r}"
    )


@pytest.mark.unit
async def test_an_ordinary_error_passes_through_unchanged() -> None:
    """The positive control: a plain range refusal carries no `ctx.error`.

    Without this, a handler that deleted `ctx` outright -- or replaced every
    entry with a placeholder -- would satisfy the test above.
    """
    exc = _real_validation_error(ZtAnswerPatch, {"maturity_stage": 9})
    original = exc.errors()
    assert original[0]["type"] == "less_than_equal", original

    # `loc` is a tuple and JSON has no tuples, so it comes back a list. That is
    # correct; asserting byte-identity across the round trip would be asserting
    # that JSON has tuples. What matters is that the fields a client reads are
    # unchanged.
    detail = (await _render(exc))["error"]["details"][0]
    assert detail["type"] == original[0]["type"]
    assert detail["loc"] == list(original[0]["loc"])
    assert detail["msg"] == original[0]["msg"]
    assert detail["ctx"] == {"le": 4}, (
        "an ordinary range refusal's ctx must survive intact, and `le` must "
        "stay an INT. A previous hand-rolled coercion stringified every ctx "
        "value, so this went out as {'le': '4'} -- a wire-format change for "
        "every client, to fix a case that only ever involved ctx['error']. "
        "This assertion pinned that regression until review caught it."
    )

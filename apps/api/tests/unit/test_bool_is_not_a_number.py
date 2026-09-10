"""Every int a client can POST must refuse `true`, and refuse it ON PURPOSE (#189).

`bool` subclasses `int`. Pydantic v2's lax mode therefore reads `true` as the
integer 1 for any `int` field, before any range check runs -- so
`PATCH /zt/answers/{id} {"maturity_stage": true}` stored **Stage 1** and
returned 200. The reasoning, and the alternative fix that was rejected, live in
`app/schemas/_numeric.py`.

## The set is DERIVED from the route table, never listed here

A hand-written list of stage and tier fields is a sample: the fields it omits
are exactly the ones that drift unnoticed. #189's own sweep note asks whoever
picks it up to "grep for constrained `int` fields carrying a stage or tier
before calling it done" -- a grep answers that once. This walks FastAPI's own
request bodies, so a new schema field is covered the day it is added rather
than the day someone remembers to come back here.

`bool` fields are excluded by construction rather than by exemption: the filter
is an identity check, and `bool is int` is False.

## Why these assert the REASON and not just the refusal

This is the discriminating half, and without it the sweep is nearly vacuous.
Before the fix, every inbound int field that refused `False` did so through a
`ge=1` or `ge=2` floor that happens to sit above zero -- an accident of range,
not a decision about type. `True` is 1 and clears any floor of 1, which is why
it landed almost everywhere.

A test asserting only "a bool is refused" would pass today on the `intake`
fields, whose `ge=2` refuses both; it would keep passing if the guard were
deleted, and go red the day someone legitimately widened a range to `ge=0`. It
would pin the bounds and not the rule. Keying on the marker separates "refused
for being a bool" from "refused because 0 is out of range", which is the only
version of this test that fails for the right reason.

## Fail-closed

The derivation walks FastAPI internals (`original_router`, `body_field`) that
are not a public contract and moved in the 0.14x line already. If a version
bump makes the walk return nothing, this file must go RED rather than report a
clean sweep over zero fields -- "I could not look" must not share an exit with
"nothing to complain about". `test_the_derivation_still_finds_request_bodies`
is that check; without it the parametrised tests below would collect zero cases
and pytest would call that success.
"""

from __future__ import annotations

from typing import Annotated, Any, get_args, get_origin

import pytest
from pydantic import BaseModel, TypeAdapter

from app.main import app
from app.schemas._numeric import BOOL_REFUSAL_MARKER


def _flatten(routes: Any, out: list[Any] | None = None) -> list[Any]:
    """Expand FastAPI's lazily-included routers into real routes."""
    out = [] if out is None else out
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            _flatten(inner.routes, out)
        else:
            out.append(route)
    return out


def _bodied_routes() -> list[Any]:
    return [r for r in _flatten(app.routes) if getattr(r, "body_field", None) is not None]


def _walk(model: Any, seen: set[type[BaseModel]]) -> None:
    """Collect `model` and every BaseModel nested inside it."""
    if not (isinstance(model, type) and issubclass(model, BaseModel)) or model in seen:
        return
    seen.add(model)
    for field in model.model_fields.values():
        for arg in _parts(field.annotation):
            _walk(arg, seen)


def _parts(annotation: Any) -> tuple[Any, ...]:
    """The constituent types of an annotation, with `Annotated` peeled off.

    `Annotated[int, BeforeValidator(...)] is int` is False, so a filter that
    does not unwrap goes blind the moment a field is annotated -- which is the
    moment it starts being guarded. That is not hypothetical: it happened on
    the first run after the fix landed. Every case dropped out of the
    parametrisation, pytest reported the two sweeps as SKIPPED rather than
    failed, and only `test_the_derivation_still_finds_request_bodies` said so.
    The fix had silently disarmed its own test, and the fail-closed check is
    the entire reason that was visible.
    """
    if get_origin(annotation) is Annotated:
        return _parts(get_args(annotation)[0])
    args = get_args(annotation)
    if not args:
        return (annotation,)
    return tuple(p for arg in args for p in _parts(arg))


def _int_fields() -> list[tuple[type[BaseModel], str, Any]]:
    """Every int-typed field on every model reachable from a request body."""
    models: set[type[BaseModel]] = set()
    for route in _bodied_routes():
        _walk(route.body_field.field_info.annotation, models)

    found = []
    for model in sorted(models, key=lambda c: (c.__module__, c.__name__)):
        for name, field in model.model_fields.items():
            # Identity, not `issubclass`: `bool is int` is False, so a declared
            # `bool` field drops out here rather than needing an exemption.
            if not any(p is int for p in _parts(field.annotation)):
                continue
            annotation = (
                Annotated[(field.annotation, *field.metadata)]
                if field.metadata
                else field.annotation
            )
            found.append((model, name, TypeAdapter(annotation)))
    return found


_INT_FIELDS = _int_fields()
_CASES = [pytest.param(m, n, a, id=f"{m.__name__}.{n}") for m, n, a in _INT_FIELDS]


@pytest.mark.unit
def test_the_derivation_still_finds_request_bodies() -> None:
    """Fail loudly if the walk stopped working, rather than sweeping nothing.

    Without this, a FastAPI upgrade renaming `original_router` or `body_field`
    turns every parametrised test below into zero collected cases -- which
    pytest reports as success.
    """
    assert _bodied_routes(), (
        "no request-body routes found. FastAPI's internals moved and "
        "`_flatten`/`_bodied_routes` must follow them. Until they do, this "
        "file proves nothing about any schema."
    )
    assert _INT_FIELDS, (
        "request bodies were found but none carries an int field. That is "
        "possible in principle and false today, so treat it as the walk being "
        "broken until you have checked by hand."
    )


@pytest.mark.unit
@pytest.mark.parametrize("model, field, adapter", _CASES)
def test_a_bool_is_refused_because_it_is_a_bool(
    model: type[BaseModel], field: str, adapter: TypeAdapter
) -> None:
    """`true` and `false` are both refused, and the reason names the type.

    The marker is what makes this discriminating -- see the module docstring.
    A refusal carrying `greater_than_equal` is the range bound talking, and
    that bound can be widened tomorrow by someone who has never read #189.
    """
    for probe in (True, False):
        with pytest.raises(Exception) as caught:
            adapter.validate_python(probe)
        assert BOOL_REFUSAL_MARKER in str(caught.value), (
            f"{model.__name__}.{field} refused {probe!r}, but not for being a "
            f"bool -- the error was {str(caught.value)!r}. If that is a range "
            f"bound, the field is unprotected the moment the range widens: "
            f"`True` is 1 and clears any floor of 1. Annotate it `IntNotBool`."
        )


@pytest.mark.unit
@pytest.mark.parametrize("model, field, adapter", _CASES)
def test_the_values_a_client_plainly_meant_still_work(
    model: type[BaseModel], field: str, adapter: TypeAdapter
) -> None:
    """The positive control, without which a guard refusing everything passes.

    `CLAUDE.md`: "Accept `2` and `2.0`: refusing a value the model plainly
    meant is the same defect facing the other way." A browser posting a
    `<select>` value sends the string spelling.

    Fields are bound at different places, so this probes a value each one
    admits rather than a fixed number -- and skips nothing: a field admitting
    no integer at all fails on the empty search rather than passing quietly.
    """
    admissible = None
    for candidate in range(0, 11):
        # noqa reason: the exception carries nothing worth logging. This is a
        # SEARCH for any value the field admits, so a rejection is the expected
        # outcome for most candidates rather than a fault. The empty-search case
        # is what gets reported, and it is asserted immediately below.
        try:
            adapter.validate_python(candidate)
        except Exception:  # noqa: S112 - see above; a rejection here is data, not an error
            continue
        admissible = candidate
        break
    assert admissible is not None, (
        f"{model.__name__}.{field} admits no integer in 0..10, so this test "
        f"cannot prove the guard left valid input alone. Widen the search or "
        f"check the field's bounds."
    )
    for spelling in (admissible, float(admissible), str(admissible)):
        assert adapter.validate_python(spelling) == admissible, (
            f"{model.__name__}.{field} rejected {spelling!r}, which is "
            f"{admissible} written another way. The guard is refusing more "
            f"than bools."
        )

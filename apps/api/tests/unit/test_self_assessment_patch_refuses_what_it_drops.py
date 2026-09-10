"""A client answer route must not return 200 for a field it discards (#195).

`PATCH /zt/self-assessment/answers/{id}` took the ADMIN `ZtAnswerPatch` body
and honoured two of its five fields. A client could send `target_stage`,
receive 200, re-read the row, and find the value gone -- with nothing anywhere
saying it was ignored. Core principle 2: "never a lie that something
succeeded."

## The dropped set was wider than the issue, in both services

#195 names `target_stage` on ZT. Listing what each handler actually reads
found more, and the one with teeth is shared by both:

    evidence_artifact_id -- a client attaches evidence, gets 200, and no
        evidence is attached.
    locked -- a client locks a row against AI reruns (Work Order C2), gets
        200, the row is not locked, and the next AI run overwrites it.

CSF has the same defect and it was not filed anywhere. It was found by putting
#195's question to the twin, which `CLAUDE.md` requires. CSF's own schema
comment already reads "lock/unlock this row against AI reruns (admin only)" --
the rule was written beside the field, and the route never enforced it.

## Both services run off one table, and the refused fields are DERIVED

Parametrising over (admin schema, client schema) pairs rather than writing two
files means the CSF and ZT cases cannot drift apart -- which is the failure
mode that produced the second half of this defect. The refused set per service
is the difference between the two schemas, so a field added to either admin
schema tomorrow joins the refusal set with nobody editing this file.

## Refused, not honoured -- a product decision with a stated reason

See `ZtSelfAssessmentAnswerPatch`. Honouring `target_stage` would create a
third writer of `ZtAnswer.target_stage`, and `zt/scoring.py::capability_target_override` carries an exemption that
expires on exactly that event (#188).
`test_refusing_holds_the_zt_writer_count_at_two` pins the consequence, so a
future author who prefers honouring has to confront #188 rather than discover
it afterwards.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.csf import CsfAnswerPatch, CsfSelfAssessmentAnswerPatch
from app.schemas.zt import ZtAnswerPatch, ZtSelfAssessmentAnswerPatch

# (service, admin schema, client schema, a field/value the client route APPLIES)
_SERVICES = [
    ("zt", ZtAnswerPatch, ZtSelfAssessmentAnswerPatch, {"maturity_stage": 2}),
    ("csf", CsfAnswerPatch, CsfSelfAssessmentAnswerPatch, {"maturity_tier": 2}),
]


def _refused(admin: type[BaseModel], client: type[BaseModel]) -> list[str]:
    """What the admin route accepts and the client route does not."""
    return sorted(set(admin.model_fields) - set(client.model_fields))


_REFUSAL_CASES = [
    pytest.param(service, admin, client, applied, field, id=f"{service}.{field}")
    for service, admin, client, applied in _SERVICES
    for field in _refused(admin, client)
]


@pytest.mark.unit
@pytest.mark.parametrize("service, admin, client, applied", _SERVICES)
def test_the_client_schema_is_actually_narrower_than_the_admin_one(
    service: str, admin: type[BaseModel], client: type[BaseModel], applied: dict
) -> None:
    """Fail loudly if the two schemas converge, rather than sweeping nothing.

    If someone widens a client schema to match its admin schema, `_refused`
    returns empty for that service and its parametrised cases below stop
    collecting -- which pytest reports as success. This is the branch that
    keeps "I could not look" distinguishable from "nothing to complain about".
    """
    assert _refused(admin, client), (
        f"{service}: the client self-assessment schema now accepts every field "
        f"the admin schema does. Either the routes were deliberately merged -- "
        f"in which case this file needs rewriting, not deleting -- or a field "
        f"was added to the wrong schema. #195 is about the gap between them."
    )
    assert set(client.model_fields) == set(applied) | {"notes"}, (
        f"{service}: the client route honours "
        f"{sorted(set(applied) | {'notes'})}. If that changed, the handler and "
        f"this schema must change together -- a field accepted and not written "
        f"is exactly #195."
    )


@pytest.mark.unit
@pytest.mark.parametrize("service, admin, client, applied, field", _REFUSAL_CASES)
def test_a_field_this_route_will_not_apply_is_refused_not_dropped(
    service: str,
    admin: type[BaseModel],
    client: type[BaseModel],
    applied: dict,
    field: str,
) -> None:
    """The discriminating assertion: 422, not a quiet 200.

    Asserting only "the value is absent from the parsed model" would pass
    against the ORIGINAL code too -- it was absent there as well, because the
    handler ignored it. What must be true is that the caller is TOLD, which is
    the whole of #195.
    """
    with pytest.raises(ValidationError) as caught:
        client(**applied, **{field: 3})
    assert field in str(caught.value), (
        f"{service}.{field} was refused, but the error does not name it, so a "
        f"client cannot tell which field to remove. A guard's message must "
        f"name the CAUSE, not the check."
    )


@pytest.mark.unit
@pytest.mark.parametrize("service, admin, client, applied, field", _REFUSAL_CASES)
def test_the_refusal_points_at_the_route_that_does_apply_it(
    service: str,
    admin: type[BaseModel],
    client: type[BaseModel],
    applied: dict,
    field: str,
) -> None:
    """A refusal leaving the caller nowhere to go is half a fix.

    These fields are settable -- just not here. The message says where, so a
    reader does not conclude the feature is missing.

    Parametrised over EVERY refused field, not the first one sorted. An earlier
    version took `_refused(...)[0]` and asserted a route string that the
    message contains unconditionally -- so it held for any input and could not
    notice a field whose refusal named the wrong remedy. Caught in review.
    """
    with pytest.raises(ValidationError) as caught:
        client(**{field: 3})
    message = str(caught.value)
    assert f"/{service}/answers/" in message, (
        f"{service}.{field}: the refusal does not name the admin route that "
        f"does apply this field. Message was: {message!r}"
    )
    assert field in message, (
        f"{service}: the refusal names a remedy but not {field}, so a caller "
        f"cannot tell which field the remedy is for. Message was: {message!r}"
    )


@pytest.mark.unit
def test_refusing_holds_the_zt_writer_count_at_two() -> None:
    """#188's exemption expires if a third writer of `target_stage` appears.

    This asserts the SHAPE keeping it alive: the client schema has no
    `target_stage` field at all, so the handler cannot acquire one by someone
    adding a line to the route. If a future author decides #195 should be
    fixed by honouring instead, this fails and points at #188 -- which is the
    confrontation that decision deserves.
    """
    assert "target_stage" not in ZtSelfAssessmentAnswerPatch.model_fields, (
        "the client self-assessment schema grew a `target_stage` field. If it "
        "is now written, this route is a THIRD writer of "
        "`ZtAnswer.target_stage` and the deliberate exemption in "
        "`zt/scoring.py::capability_target_override` has expired -- #188 must "
        "be fixed in the same change, not left latent."
    )


@pytest.mark.unit
@pytest.mark.parametrize("service, admin, client, applied", _SERVICES)
def test_what_the_route_does_apply_still_works(
    service: str, admin: type[BaseModel], client: type[BaseModel], applied: dict
) -> None:
    """The positive control. A schema refusing everything would pass the rest."""
    field, value = next(iter(applied.items()))
    patched = client(**applied, notes="checked")
    assert getattr(patched, field) == value
    assert patched.notes == "checked"
    # The string spelling a browser `<select>` actually posts.
    assert getattr(client(**{field: str(value)}), field) == value


@pytest.mark.unit
@pytest.mark.parametrize("service, admin, client, applied", _SERVICES)
def test_the_client_route_refuses_a_bool_too(
    service: str, admin: type[BaseModel], client: type[BaseModel], applied: dict
) -> None:
    """#189 and #195 meet here: the narrow schemas inherit the bool guard.

    A new schema is the easiest place to reintroduce a fixed defect, because
    it is written fresh and the annotation is easy to leave off.
    """
    field = next(iter(applied))
    with pytest.raises(ValidationError) as caught:
        client(**{field: True})
    assert "boolean" in str(caught.value).lower(), (
        f"{service}: the client route accepts `true` as a score. That is #189, "
        f"reintroduced in the schema written to fix #195."
    )

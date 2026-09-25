"""A schema-level refusal carries a typed reason too (#285).

Core principle 2: user-facing API errors are typed (`{reason, message}`, the
D-016 pattern) and "never raw validation dumps". Every hand-written refusal on
the client self-assessment routes follows it -- `target_stage_out_of_range` is
one. The two refusals added for #195 are DERIVED from the schema instead
(`extra="forbid"` plus a validator reading `model_fields`, which is what makes
it impossible for a newly-added field to start being silently dropped), so the
caller received Pydantic's shape and had to sniff strings to tell one cause from
another.

The repair is the wider of the two the issue offered: synthesise the reason in
`_handle_validation_error`, which fixes every schema-level 422 in the API rather
than the two that prompted it, and keeps the derived refusal set. Moving the
refusal into the handler as a typed `HTTPException` would have reintroduced the
enumeration the schema exists to avoid.

## Why these tests go through HTTP

`RequestValidationError`'s shape is Pydantic's, and a test that built one by
hand would be asserting my reading of it. The defect this family keeps producing
lives in the RESPONSE -- `_jsonable_validation_errors`' own docstring records a
500 thrown from inside the 422 handler that every schema-level assertion passed
over. So these post real payloads to real routes and read the body.
"""

from __future__ import annotations

import os
import uuid as _uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.unit


@pytest.fixture()
def client(tmp_path) -> Iterator[TestClient]:
    url = f"sqlite:///{tmp_path / 'shield-422.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _headers(c: TestClient) -> dict[str, str]:
    """An admin bearer plus the tenant header the client routes require.

    The header is not decoration: dependencies resolve BEFORE request
    validation, so without it these routes answer 400 and every assertion below
    would be about the wrong refusal.
    """
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    bearer = r.json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        json={"legal_name": "Atlas"},
        headers={"Authorization": f"Bearer {bearer}"},
    ).json()["id"]
    return {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}


def _error(resp) -> dict:
    assert resp.status_code == 422, resp.text
    return resp.json()["error"]


def test_a_forbidden_extra_field_names_its_cause(client) -> None:
    """The refusal #195 added, read the way an integrator reads it.

    `schema_unapplied_fields` is a code a client maps to copy (the
    `mode="before"` validator runs ahead of `extra="forbid"`, so it is not
    `schema_extra_forbidden`). "Extra inputs are
    not permitted" is a sentence a client matches on, and matching on a sentence
    is what breaks the day the sentence is reworded -- a defect this repo has
    already shipped once, in a spec that could never match again.
    """
    headers = _headers(client)
    resp = client.patch(
        f"/zt/self-assessment/answers/{_uuid.uuid4()}",
        json={"maturity_stage": 2, "target_stage": 4},
        headers=headers,
    )
    error = _error(resp)

    # MEASURED, not assumed. The `mode="before"` validator runs AHEAD of
    # `extra="forbid"`, so the code a client receives is the named-cause one
    # rather than Pydantic's generic forbidden-extra. An earlier version of this
    # test expected `schema_extra_forbidden` and was written from the issue's
    # description instead of from a run -- it failed, which is the only reason
    # the ordering is documented anywhere.
    assert error["reason"] == "schema_unapplied_fields"
    assert error["reasons"] == ["schema_unapplied_fields"]
    # The envelope is ADDITIVE. A consumer reading the old shape still works.
    assert error["code"] == 422
    assert error["message"] == "Request validation failed."
    assert error["details"], "the raw detail must survive; the reason is beside it, not instead"


def test_a_range_refusal_gets_its_own_code_not_the_same_one(client) -> None:
    """The discriminator. One code for every schema failure would be no code.

    Without this, an implementation that hardcoded `schema_invalid` would pass
    the test above and tell a client nothing they could act on -- which is the
    state #285 describes, wearing a `reason` key.
    """
    headers = _headers(client)
    resp = client.patch(
        f"/zt/self-assessment/answers/{_uuid.uuid4()}",
        json={"maturity_stage": 99},
        headers=headers,
    )
    error = _error(resp)

    assert error["reason"].startswith("schema_")
    assert error["reason"] != "schema_unapplied_fields"
    assert error["reason"] != "schema_multiple"


def test_two_different_causes_are_not_collapsed_into_one(client) -> None:
    """A mixed failure must not pick one cause and discard the rest.

    That is how a client comes to render "unknown field" over a request that
    ALSO had a value out of range, and then a consultant fixes the field name
    and gets the same 422 again with no idea why.
    """
    # Two FIELD errors, not an unknown key beside one. A `mode="before"`
    # validator that raises short-circuits the whole model, so a payload
    # carrying an unapplied field never produces a second error at all -- which
    # is worth knowing, and is why this payload is shaped the way it is rather
    # than the obvious way.
    headers = _headers(client)
    resp = client.patch(
        f"/zt/self-assessment/answers/{_uuid.uuid4()}",
        json={"maturity_stage": 99, "notes": 5},
        headers=headers,
    )
    error = _error(resp)

    assert error["reason"] == "schema_multiple"
    assert len(error["reasons"]) >= 2, error["reasons"]
    assert len(set(error["reasons"])) == len(error["reasons"])


def test_the_csf_twin_behaves_identically(client) -> None:
    """Both twins, because one typed and one not makes an integrator distrust both.

    CSF has no per-capability target, so the extra field differs -- the SHAPE of
    the answer must not.
    """
    headers = _headers(client)
    resp = client.patch(
        f"/csf/self-assessment/answers/{_uuid.uuid4()}",
        json={"maturity_tier": 2, "target_tier": 4},
        headers=headers,
    )
    error = _error(resp)

    assert error["reason"] == "schema_unapplied_fields"


def test_every_detail_entry_gets_a_code(client) -> None:
    """`reasons` summarises the details, so it must not be SHORTER than they are.

    An entry whose `type` is missing or empty yields `schema_unknown` rather
    than being skipped: skipping would let a client checking "did every error
    get a code" be told yes over an error that got none, which is the silent
    discard this handler exists to end. Asserted against the real payload rather
    than by unit-testing the helper alone, so a route whose errors carry an
    unusual shape is covered too.
    """
    from app.exceptions import schema_reasons

    headers = _headers(client)
    resp = client.patch(
        f"/zt/self-assessment/answers/{_uuid.uuid4()}",
        json={"maturity_stage": 99, "notes": 5},
        headers=headers,
    )
    error = _error(resp)

    assert set(error["reasons"]) == set(schema_reasons(error["details"]))
    assert len(error["reasons"]) == len(set(error["reasons"])), "distinct, in first-seen order"
    # The first reason is the first error Pydantic reported, read off the
    # details rather than off the function under test. This payload's two types
    # are already in alphabetical order, so this line alone cannot tell
    # first-seen from sorted; the route-level ORDER is pinned by
    # test_reasons_keep_first_seen_order_through_the_route (#318).
    assert error["reasons"][0] == "schema_" + error["details"][0]["type"], error

    # The no-type case, which a live route may never produce and which the
    # helper must still handle rather than drop.
    assert schema_reasons([{"loc": ["body"]}]) == ["schema_unknown"]
    assert schema_reasons([{"type": ""}]) == ["schema_unknown"]


def test_a_hand_written_refusal_is_untouched(client) -> None:
    """The other half of the convention, and the reason for the prefix.

    D-016 reasons are chosen strings. Pydantic's `type` vocabulary is not ours,
    so a future version could add one that collides -- and a client mapping
    `reason` to copy would render a schema failure as a domain refusal. The
    `schema_` namespace makes that impossible by construction rather than by
    nobody having picked the same word yet.

    ## This test used to prove nothing, and the reason is worth keeping

    It posted `{"target_stage": 99}` to `/zt/self-assessment/submit` and
    guarded its assertion with `if reason is not None and status != 422`.
    Three things were wrong with that, discovered in that order:

    1. **The URL does not exist.** The route is
       `/zt/services/{service_id}/self-assessment/submit`. MEASURED: that POST
       answers **404** with `{"error": {"code": 404, "message": "Not Found"}}`
       and no `reason` key at all, so the guard's first clause was false and
       the assertion never ran. The request never reached a route.
    2. **The annotation left on it was also wrong.** It said `target_stage: 99`
       "fails `Field(ge=1, le=4)`, so this route always answers 422". It never
       reaches schema validation either.
    3. **The remedy proposed for it was wrong too** -- send a schema-VALID
       value the route refuses, `target_stage=4` against a DoD ZTRA assessment.
       That refusal is `HTTP_422_UNPROCESSABLE_ENTITY`, so `status != 422` is
       STILL false and the assertion would still never run.

    Point 3 is the load-bearing one: **a hand-written D-016 refusal can be a
    422.** `target_stage_out_of_range` is one. So the HTTP STATUS cannot
    separate "schema rejection" from "hand-written refusal", and a guard built
    on it is not merely unreachable here -- it is asking a question that has no
    answer. The two tests below replace it: one reaches that refusal for real,
    and one asserts the property over the whole set rather than one case.
    """
    headers = _headers(client)

    # A DoD ZTRA service: its ladder ends at stage 3, while
    # `ZtSelfAssessmentSubmit.target_stage` is bound `ge=1, le=4` for both
    # frameworks because a field constraint cannot see the service. Stage 4 is
    # therefore SCHEMA-VALID and domain-invalid -- the only shape that reaches a
    # hand-written refusal on this route.
    svc = client.post(
        "/zt/services",
        json={"kind": "zero_trust_dod", "title": "ZT DoD"},
        headers=headers,
    )
    assert svc.status_code in (200, 201), svc.text
    service_id = svc.json()["id"]
    created = client.post(f"/zt/services/{service_id}/assessments", headers=headers)
    assert created.status_code in (200, 201), created.text

    resp = client.post(
        f"/zt/services/{service_id}/self-assessment/submit",
        json={"target_stage": 4},
        headers=headers,
    )

    # ASSERT WHAT THE FILTER SELECTED BEFORE READING ITS RESULT. The old test's
    # whole failure was a condition that silently selected nothing, so the
    # precondition is an assertion here rather than a guard.
    assert resp.status_code == 422, (
        "this test needs the hand-written range refusal; if the route now "
        f"answers {resp.status_code} it has changed and this no longer "
        f"exercises what it claims. body={resp.text}"
    )
    reason = resp.json()["error"]["reason"]

    # The refusal is hand-written -- it names the framework and the stage.
    assert reason == "target_stage_out_of_range", resp.text
    # ...and it arrives at 422, which is the fact that made the old
    # status-based guard incoherent. Pinned so the point cannot be lost.
    assert not reason.startswith("schema_"), (
        "a hand-written D-016 refusal must never be mistaken for a " "synthesised schema code"
    )


def test_no_hand_written_reason_anywhere_squats_on_the_schema_namespace() -> None:
    """The claim the test above can only sample: collision is impossible.

    One route proves one route. "The `schema_` namespace makes that impossible
    by construction" is a claim about EVERY hand-written refusal in the API, so
    it is asserted over the derived set rather than over the case someone
    happened to write a test for -- the enumeration-versus-derivation rule in
    `CLAUDE.md`, applied to a test's population.

    Goes red the day anyone writes `"reason": "schema_..."` by hand, which is
    the only way the two namespaces can ever meet.

    ## Scope, stated rather than left to be inferred

    `app/exceptions.py` is EXCLUDED, and it is the one file that must be: it is
    the synthesiser, so producing `schema_` codes is its job. Excluding it is
    the point of the test, not a hole in it. Every other module under `app/` is
    in scope -- routes, schemas and services alike, because a typed refusal can
    be raised from any of them and a route-only sweep would be an enumeration
    of where refusals live today.
    """
    import re

    app_dir = Path(__file__).resolve().parents[2] / "app"
    assert app_dir.is_dir(), f"cannot find the app package at {app_dir}"

    # BOTH FORMS a hand-written reason takes in this repo. The first version
    # matched only `"reason": "code"` and therefore reported clean over
    # `oidc_jwks_unavailable`, which is written as a CONSTRUCTOR KWARG in
    # `app/security/oidc.py` and surfaced verbatim by `routes/oidc.py` as
    # `detail={"reason": exc.reason, ...}` -- a live, client-reaching D-016
    # code the sweep could not see. `oidc_token_invalid` was found only
    # because `routes/oidc.py` separately spells it as a literal.
    #
    # The scope was generalised over the DIRECTORY ("every other module under
    # `app/`") and left enumerated over the FORM, and the one service module
    # that raises typed refusals is the one the form missed. CLAUDE.md's
    # "the sweep predicate was a PATH instead of a defect", arriving at the
    # other axis.
    # A NEGATIVE LOOKBEHIND, not `\b`. The first attempt wrote `\b` and it
    # reached the file as a literal BACKSPACE byte (U+0008) inside the raw
    # string, so the alternation read `<BS>reason\s*=` and matched nothing --
    # the sweep silently lost the entire kwarg form it had just been widened
    # to cover, and `grep` showed a correct-looking line because a backspace
    # renders as nothing. Caught by `check_no_control_chars.py`, which exists
    # for exactly this and reported `339: U+0008`.
    #
    # The lookbehind also does the job `\b` was there for: it stops
    # `rejected_reason=` being read as a reason code.
    literal = re.compile(
        r"""(?:["']reason["']\s*:|(?<![A-Za-z0-9_])reason\s*=)""" r"""\s*["']([A-Za-z0-9_]+)["']"""
    )
    found: dict[str, str] = {}
    scanned = 0
    for path in sorted(app_dir.rglob("*.py")):
        # Compared as a PATH, not a basename: `path.name` would also exempt a
        # future `app/<pkg>/exceptions.py`, silently, and the exemption is
        # meant to cover the ONE synthesiser.
        if path == app_dir / "exceptions.py":
            continue
        scanned += 1
        for code in literal.findall(path.read_text(encoding="utf-8")):
            found.setdefault(code, str(path.relative_to(app_dir)))

    # FAIL CLOSED. An empty sweep is "I could not look", never "nothing to
    # complain about" -- if a refactor moves these or this path breaks, the
    # test must say so rather than pass on nothing.
    # FLOORS SET FROM THE MEASURED VALUES, not from caution. At the time of
    # writing the sweep reads 131 modules and finds 47 distinct codes, so
    # these sit well below the truth (a refactor must not redden them) and
    # well above zero (a broken pattern must). A floor of 5 against 47 would
    # have let the pattern lose 90% of its population in silence.
    assert scanned > 50, f"only scanned {scanned} modules under {app_dir}; the sweep is broken"
    assert len(found) >= 25, (
        f"found only {len(found)} hand-written reason codes under {app_dir}. "
        "This repo has many; a sweep this thin means the pattern stopped "
        "matching, not that the codes went away."
    )

    # THE RESIDUAL, stated rather than left implied. A code held in a module
    # CONSTANT and referenced by name is unreachable by any reason-keyed text
    # scan -- `AI_CALL_FAILED = "ai_call_failed"` in `app/ai/failures.py` and
    # `_NO_CITATION` in `app/attack/pending.py` are both used as
    # `"reason": AI_CALL_FAILED`, and neither constant's VALUE is visible
    # here. Writing this down is what stops the next reader believing the
    # sweep is total; closing it would mean resolving constants, which is a
    # different tool.
    squatters = {c: where for c, where in found.items() if c.startswith("schema_")}
    assert squatters == {}, (
        "these hand-written D-016 reasons sit inside the synthesised schema "
        f"namespace, so a client cannot tell them apart: {squatters}"
    )


def test_the_schema_namespace_is_the_literal_the_web_layer_spells_out() -> None:
    """Pins the cross-language duplicate from the Python side.

    `SCHEMA_REASON_PREFIX` is written in two languages with no build step
    between them. `SignUpForm.test.tsx` spells the literal out, so a TS-side
    edit goes red; until this test existed a PYTHON-side edit went red nowhere,
    because every test that used the constant imported it and followed it.

    The width of that gap is #317: change this prefix without changing the
    component and "Request validation failed." returns under the Email field of
    the public sign-up page. A comment in `exceptions.py` names the duplicate,
    and a comment is not a gate.

    Both literals are written out here on purpose. Comparing the module's value
    against an independently-spelled string is a real assertion; comparing it
    against itself is the shape this file's own fixtures exist to catch.
    """
    from app import exceptions

    assert exceptions.SCHEMA_REASON_PREFIX == "schema_"
    assert exceptions.SCHEMA_REASON_MIXED == "schema_multiple"
    # And the relationship between them, which is what the component relies on:
    # the mixed code must live INSIDE the namespace, or a multi-field failure
    # would be treated as friendly copy.
    assert exceptions.SCHEMA_REASON_MIXED.startswith("schema_")


def test_schema_reasons_keeps_first_seen_order_and_drops_repeats() -> None:
    """The documented contract, against literal input: order preserved, repeats
    dropped, a missing type named rather than skipped (#318)."""
    from app.exceptions import schema_reasons

    details = [
        {"type": "string_type"},
        {"type": "less_than_equal"},
        {"type": "string_type"},
        {},
    ]
    assert schema_reasons(details) == [
        "schema_string_type",
        "schema_less_than_equal",
        "schema_unknown",
    ]


def test_reasons_keep_first_seen_order_through_the_route(client) -> None:
    """The ORDER at the surface a client reads (#318, round 1 of PR 610).

    A bool for `maturity_stage` fails a VALUE check and an int for `notes` a
    TYPE check: first-seen is value_error then string_type, which `sorted()`
    reverses. The expectation is written out, not derived.
    """
    headers = _headers(client)
    resp = client.patch(
        f"/zt/self-assessment/answers/{_uuid.uuid4()}",
        json={"maturity_stage": True, "notes": 5},
        headers=headers,
    )
    error = _error(resp)
    assert error["reasons"] == ["schema_value_error", "schema_string_type"], error
    assert error["reason"] == "schema_multiple", error


def test_several_errors_of_one_type_are_that_type_not_mixed(client) -> None:
    """The same-type branch of the `reason` choice (#318's advisory): several
    errors of ONE type are that type's code, not `schema_multiple`. Through a
    real route: an empty registration body is three `missing` errors."""
    resp = client.post("/auth/register", json={})
    error = _error(resp)
    assert len(error["details"]) >= 2, error
    assert error["reason"] == "schema_missing", error
    assert error["reasons"] == ["schema_missing"], error

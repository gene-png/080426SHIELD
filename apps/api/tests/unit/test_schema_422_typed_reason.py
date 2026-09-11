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

    `schema_extra_forbidden` is a code a client maps to copy. "Extra inputs are
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
    """
    from app.exceptions import SCHEMA_REASON_PREFIX

    headers = _headers(client)
    resp = client.post(
        "/zt/self-assessment/submit",
        json={"target_stage": 99},
        headers=headers,
    )
    # Whatever this route answers, a schema code and a domain code cannot be the
    # same string.
    body = resp.json()
    reason = body.get("error", {}).get("reason")
    if reason is not None and resp.status_code != 422:
        assert not reason.startswith(SCHEMA_REASON_PREFIX), (
            "a hand-written D-016 refusal must never be mistaken for a " "synthesised schema code"
        )

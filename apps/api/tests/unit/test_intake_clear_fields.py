"""#1093 item 1: an intake field the client empties is CLEARED, not refused.

`ClientProfilePatch` says "Strings normalize to None when empty so the user can
clear a field by tabbing through with nothing in it". Before this, only
`legal_name` did: a whitespace-only website stripped to `""` and `HttpUrl`
refused it with a 422, and every other text field stored the blanks. Asserted
on the stored column, through the real endpoint, so the test goes red if the
normaliser is deleted or the route stops validating through the model.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.client import Client
from tests.unit.test_intake_routes import (
    _register_and_bearer,
    app_client,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.unit

# Every plain text field Step 2 and Step 4 of the wizard save. Listed from the
# wizard's inputs, not from the schema, so a field the schema forgets shows up.
_TEXT_FIELDS = [
    "dba_name",
    "size_band",
    "industry",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "postal_code",
    "country",
    "prompting_context",
]


def _patch(client, bearer: str, fields: dict):
    return client.patch(
        "/intake",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"client": fields},
    )


def _stored(TestSession, field: str):
    with TestSession() as db:
        return getattr(db.execute(select(Client)).scalar_one(), field)


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_an_emptied_website_is_cleared_not_refused(app_client, blank) -> None:  # noqa: F811
    client, TestSession = app_client
    bearer = _register_and_bearer(client)
    assert _patch(client, bearer, {"website": "kentro.com"}).status_code == 200
    assert _stored(TestSession, "website") == "https://kentro.com/"

    r = _patch(client, bearer, {"website": blank})
    assert r.status_code == 200, r.text
    assert _stored(TestSession, "website") is None


@pytest.mark.parametrize("field", _TEXT_FIELDS)
@pytest.mark.parametrize("blank", ["", "   "])
def test_an_emptied_text_field_is_stored_as_null(app_client, field, blank) -> None:  # noqa: F811
    client, TestSession = app_client
    bearer = _register_and_bearer(client)
    assert _patch(client, bearer, {field: "x1"}).status_code == 200
    assert _stored(TestSession, field) == "x1"

    r = _patch(client, bearer, {field: blank})
    assert r.status_code == 200, r.text
    assert _stored(TestSession, field) is None


@pytest.mark.parametrize("field", ["website", *_TEXT_FIELDS])
def test_null_clears_a_field(app_client, field) -> None:  # noqa: F811
    """The wire form the wizard now sends for an emptied field (item 1's web
    half). Pinned so the API keeps honouring it."""
    client, TestSession = app_client
    bearer = _register_and_bearer(client)
    value = "kentro.com" if field == "website" else "x1"
    assert _patch(client, bearer, {field: value}).status_code == 200
    assert _stored(TestSession, field) is not None

    r = _patch(client, bearer, {field: None})
    assert r.status_code == 200, r.text
    assert _stored(TestSession, field) is None


def test_a_non_blank_value_is_stored_as_typed(app_client) -> None:  # noqa: F811
    """The normaliser maps blanks only: it does not strip real values."""
    client, TestSession = app_client
    bearer = _register_and_bearer(client)
    assert _patch(client, bearer, {"city": "  Springfield "}).status_code == 200
    assert _stored(TestSession, "city") == "  Springfield "

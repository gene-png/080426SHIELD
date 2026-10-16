"""#1198 item 1: Step 3's title and phone can be cleared; display_name and
timezone cannot.

Ruled on #736 (6216024281): "title and phone are clearable; display_name is
not". `users.title` and `users.phone` are nullable; `users.timezone` is NOT
NULL, and `display_name` is the person's name on every record. Before this,
`_apply_profile_fields` skipped every None, so an emptied title or phone was a
no-op and the old value came back on reload. Asserted on the stored column,
through the real endpoint.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.user import User
from tests.unit.test_intake_routes import (
    _register_and_bearer,
    app_client,  # noqa: F401  (fixture)
)

pytestmark = pytest.mark.unit


def _patch(client, bearer: str, body: dict):
    return client.patch(
        "/intake",
        headers={"Authorization": f"Bearer {bearer}"},
        json=body,
    )


def _user_id(TestSession, field: str, value: str):
    with TestSession() as db:
        return db.execute(select(User.id).where(getattr(User, field) == value)).scalar_one()


def _stored(TestSession, user_id, field: str):
    with TestSession() as db:
        return getattr(db.get(User, user_id), field)


@pytest.mark.parametrize("field", ["title", "phone"])
@pytest.mark.parametrize("cleared", [None, "", "   "])
def test_title_and_phone_are_cleared(app_client, field, cleared) -> None:  # noqa: F811
    client, TestSession = app_client
    bearer = _register_and_bearer(client)
    assert _patch(client, bearer, {field: "x1198"}).status_code == 200
    user_id = _user_id(TestSession, field, "x1198")

    r = _patch(client, bearer, {field: cleared})
    assert r.status_code == 200, r.text
    assert _stored(TestSession, user_id, field) is None
    # The response the wizard re-reads says so too.
    assert r.json()["contact"][field] is None


@pytest.mark.parametrize("field", ["title", "phone"])
@pytest.mark.parametrize("cleared", [None, "", "   "])
def test_submit_clears_title_and_phone_too(app_client, field, cleared) -> None:  # noqa: F811
    """The submit twin (review of a2b50ccc): `POST /intake/submit` applies the
    same profile fields through `_apply_profile_fields`, and validates them
    through `IntakeSubmitRequest`, whose blank normaliser is its own."""
    client, TestSession = app_client
    bearer = _register_and_bearer(client)
    assert _patch(client, bearer, {field: "x1198"}).status_code == 200
    user_id = _user_id(TestSession, field, "x1198")

    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {"legal_name": "Atlas Defense Solutions"},
            "service_requests": [{"service_type": "consultation"}],
            field: cleared,
        },
    )
    assert r.status_code == 200, r.text
    assert _stored(TestSession, user_id, field) is None


@pytest.mark.parametrize("field", ["title", "phone"])
def test_an_unsent_title_or_phone_is_left_alone(app_client, field) -> None:  # noqa: F811
    client, TestSession = app_client
    bearer = _register_and_bearer(client)
    assert _patch(client, bearer, {field: "x1198"}).status_code == 200
    user_id = _user_id(TestSession, field, "x1198")

    assert _patch(client, bearer, {"client": {"city": "Springfield"}}).status_code == 200
    assert _stored(TestSession, user_id, field) == "x1198"


@pytest.mark.parametrize("field", ["display_name", "timezone"])
def test_display_name_and_timezone_are_not_cleared_by_null(app_client, field) -> None:  # noqa: F811
    client, TestSession = app_client
    bearer = _register_and_bearer(client)
    value = "x1198" if field == "display_name" else "America/Chicago"
    assert _patch(client, bearer, {field: value}).status_code == 200
    user_id = _user_id(TestSession, field, value)

    r = _patch(client, bearer, {field: None})
    assert r.status_code == 200, r.text
    assert _stored(TestSession, user_id, field) == value

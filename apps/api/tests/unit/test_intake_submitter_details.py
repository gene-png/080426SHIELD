"""#1282: the intake state carries the submitter's OWN account details, apart
from the effective contact.

Step 3's "your details" inputs were filled from `contact`, which
`_effective_contact` builds from the primary-contact override once one names
someone. Each input saves on blur, so tabbing through Step 3 wrote the
override's name, title and phone onto the submitter's own account. The state
now also carries `submitter`: the user's own values, never the override's.
Through the real endpoint.
"""

from __future__ import annotations

import pytest

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


def test_submitter_is_the_users_own_details_under_an_override(app_client) -> None:  # noqa: F811
    client, _ = app_client
    bearer = _register_and_bearer(client)
    assert _patch(client, bearer, {"title": "Own Title", "phone": "555-0001"}).status_code == 200
    r = _patch(
        client,
        bearer,
        {
            "client": {
                "primary_contact_name": "Dana Director",
                "primary_contact_title": "Override Title",
                "primary_contact_phone": "555-0199",
            }
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # The effective contact is the override, as before.
    assert body["contact"]["is_override"] is True
    assert body["contact"]["display_name"] == "Dana Director"
    assert body["contact"]["title"] == "Override Title"
    # The submitter is the account's own row, untouched by the override.
    submitter = body["submitter"]
    assert submitter["is_override"] is False
    assert submitter["display_name"] != "Dana Director"
    assert submitter["title"] == "Own Title"
    assert submitter["phone"] == "555-0001"

    # GET carries it too, which is what the wizard loads Step 3 from.
    g = client.get("/intake", headers={"Authorization": f"Bearer {bearer}"})
    assert g.status_code == 200, g.text
    assert g.json()["submitter"]["title"] == "Own Title"


def test_submitter_equals_contact_without_an_override(app_client) -> None:  # noqa: F811
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = _patch(client, bearer, {"title": "Own Title"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["contact"]["is_override"] is False
    assert body["submitter"] == body["contact"]


def test_submit_answers_with_the_submitter_too(app_client) -> None:  # noqa: F811
    """The submit site sets `submitter` as well (review of 9e435608)."""
    client, _ = app_client
    bearer = _register_and_bearer(client)
    assert _patch(client, bearer, {"title": "Own Title"}).status_code == 200
    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {
                "legal_name": "Atlas Defense Solutions",
                "primary_contact_name": "Dana Director",
                "primary_contact_title": "Override Title",
            },
            "service_requests": [{"service_type": "consultation"}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["contact"]["title"] == "Override Title"
    assert body["submitter"]["title"] == "Own Title"

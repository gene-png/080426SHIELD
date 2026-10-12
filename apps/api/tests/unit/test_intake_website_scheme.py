"""IN-1 (#1049), ruling A (#736 6115773247): a website typed without a scheme
is accepted with `https://` in front, on save AND submit.

Before this, `PATCH /intake` refused "kentro.com" with a schema 422, the wizard
showed "Couldn't save: Network error." on every later step, and the website was
never stored. Exercised through the real endpoints, so the test goes red if the
validator is deleted or the routes stop using `ClientProfilePatch`.
"""

from __future__ import annotations

import pytest

from tests.unit.test_intake_routes import (
    _register_and_bearer,
    app_client,  # noqa: F401  (fixture)
)


def _patch_website(client, bearer: str, website: str | None):
    return client.patch(
        "/intake",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"client": {"website": website}},
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("kentro.com", "https://kentro.com/"),
        ("www.kentro.com", "https://www.kentro.com/"),
        ("kentro.com/about", "https://kentro.com/about"),
        ("  kentro.com  ", "https://kentro.com/"),
    ],
)
def test_save_adds_https_when_no_scheme(app_client, typed, stored) -> None:  # noqa: F811
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = _patch_website(client, bearer, typed)
    assert r.status_code == 200, r.text
    assert r.json()["client"]["website"] == stored


@pytest.mark.unit
@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("https://kentro.com", "https://kentro.com/"),
        ("http://kentro.com", "http://kentro.com/"),
        ("HTTPS://kentro.com", "https://kentro.com/"),
    ],
)
def test_save_keeps_a_scheme_the_client_typed(app_client, typed, stored) -> None:  # noqa: F811
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = _patch_website(client, bearer, typed)
    assert r.status_code == 200, r.text
    assert r.json()["client"]["website"] == stored


@pytest.mark.unit
def test_save_still_refuses_a_value_that_is_not_a_web_address(app_client) -> None:  # noqa: F811
    # The prefix only supplies a missing scheme; it does not make garbage valid.
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = _patch_website(client, bearer, "not a website")
    assert r.status_code == 422, r.text
    assert r.json()["error"]["reason"].startswith("schema_")


@pytest.mark.unit
def test_save_of_null_website_still_clears_it(app_client) -> None:  # noqa: F811
    client, _ = app_client
    bearer = _register_and_bearer(client)
    assert _patch_website(client, bearer, "kentro.com").status_code == 200
    r = _patch_website(client, bearer, None)
    assert r.status_code == 200, r.text
    assert r.json()["client"]["website"] is None


@pytest.mark.unit
def test_submit_adds_https_to_a_website_without_a_scheme(app_client) -> None:  # noqa: F811
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {"legal_name": "Atlas Defense Solutions", "website": "kentro.com"},
            "service_requests": [{"service_type": "tech_debt"}],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["client"]["website"] == "https://kentro.com/"
    # And it is what was stored, not only what the response echoed.
    again = client.get("/intake", headers={"Authorization": f"Bearer {bearer}"})
    assert again.json()["client"]["website"] == "https://kentro.com/"

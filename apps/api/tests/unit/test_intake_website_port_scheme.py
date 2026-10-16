"""#1116: a website whose text before the first colon is literally "http" or
"https" is REFUSED, whatever follows the colon.

`_ATTEMPTED_SCHEME` reads a colon followed by a digit as a port
("example.com:8080"). When the word before that colon is itself the scheme
name, the reading is wrong: "https:8080" got the `https://` prefix and was
stored with host "https", and the wizard said Saved. Left to `HttpUrl` alone
it is no better: it reads "https:8080" as an IPv4 address. A typed scheme with
no "//" is a typo, not a host, so it is refused with the schema 422 the wizard
shows as "This value was not accepted, so it was not saved.".

Through the real endpoint, asserted on the response and the stored column.
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


def _patch_website(client, bearer: str, website: str):
    return client.patch(
        "/intake",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"client": {"website": website}},
    )


@pytest.mark.parametrize(
    "typed",
    ["https:8080", "http:443/x", "HTTPS:8080", "https:8080/about", " http:80 "],
)
def test_a_bare_scheme_and_a_port_is_refused(app_client, typed) -> None:  # noqa: F811
    client, TestSession = app_client
    bearer = _register_and_bearer(client)
    r = _patch_website(client, bearer, typed)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["reason"].startswith("schema_")
    with TestSession() as db:
        assert db.execute(select(Client)).scalar_one().website is None


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        # A real host with a port still gets the prefix (the reading #1116
        # must not break), and so does a host that merely starts with "http".
        ("example.com:8080", "https://example.com:8080/"),
        ("httpbin.org:8080", "https://httpbin.org:8080/"),
        ("https://kentro.com:8443", "https://kentro.com:8443/"),
    ],
)
def test_a_host_with_a_port_is_still_accepted(app_client, typed, stored) -> None:  # noqa: F811
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = _patch_website(client, bearer, typed)
    assert r.status_code == 200, r.text
    assert r.json()["client"]["website"] == stored
